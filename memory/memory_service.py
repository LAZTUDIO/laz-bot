"""Unified memory service"""
import asyncio, re, logging, os, time
from .short_term import ShortTermMemory
from .long_term import LongTermMemory
from .episodic_graph import EpisodicGraph
from .forgetting import ForgettingScheduler
from .embedding_client import EmbeddingClient
from .pad_model import PADEmotionModel, PADState
from .personality import SBTIEngine, TYPES

logger = logging.getLogger("laz-bot.memory")

STOP_WORDS = {"这个","那个","什么","怎么","可以","没有","就是","一个","我们","他们","自己","知道","因为","所以","但是","如果","虽然","而且"}

class MemoryService:
    def __init__(self, config: dict):
        mc = config.get("memory", {})
        db = mc.get("db_path") or os.environ.get("LAZ_DB", os.path.join(os.path.dirname(__file__), "..", "data", "fusion_memory.db"))
        self.short_term = ShortTermMemory(max_rounds=mc.get("short_term_max_rounds", 50))
        self.long_term = LongTermMemory(db_path=db)
        self.graph = EpisodicGraph(db_path=db)
        self.embedding = EmbeddingClient()
        fc = config.get("memory", {}).get("forgetting", {})

        # ── PAD 情绪模型 ──
        pad_cfg = config.get("personality", {}).get("pad", {})
        baseline = PADState(
            pleasure=pad_cfg.get("pleasure", 0.1),
            arousal=pad_cfg.get("arousal", -0.1),
            dominance=pad_cfg.get("dominance", 0.3),
        )
        self.pad = PADEmotionModel(
            baseline=baseline,
            decay_rate=pad_cfg.get("decay_rate", 0.3),
            lr=pad_cfg.get("lr", 0.15),
        )

        # ── SBTI 人格引擎 ──
        pers_cfg = config.get("personality", {})
        initial = pers_cfg.get("active", "OJBK")
        self.personality = SBTIEngine(
            code=initial,
            evolution_enabled=pers_cfg.get("evolution", False),
            impacts=pers_cfg.get("impacts", {}),
        )

        # 人格影响PAD基线
        self._sync_pad_baseline()

        self.forgetting = ForgettingScheduler(
            long_term_memory=self.long_term,
            episodic_graph=self.graph,
            halflife_base=fc.get("halflife_base", 7),
            archive_threshold=fc.get("archive_threshold", 0.05),
            cleanup_after_days=fc.get("cleanup_after_days", 90))

        # 人格影响遗忘速度（必须在 forgetting 之后）
        self._sync_forgetting()

        # 设置 PAD 基线到人格模板
        self._sync_pad_baseline()
        self._sync_forgetting()

        self.initialized = False

    def _sync_pad_baseline(self):
        """让人格的PAD基线生效（有开关控制）"""
        if self.personality.is_impact_enabled("pad_baseline"):
            sysp = self.personality.get_impact()
            pad = sysp.get("pad", [0.1, -0.1, 0.3])
        else:
            pad = [0.0, 0.0, 0.0]
        self.pad.set_baseline(pad[0], pad[1], pad[2])

    def _sync_forgetting(self):
        """人格影响遗忘半衰期（有开关控制）"""
        if self.personality.is_impact_enabled("memory_decay"):
            sysp = self.personality.get_impact()
            # 用 structure 逆映射为遗忘速度（结构高→记得牢→半衰期长）
            structure = sysp.get("structure", 0.5)
            halflife_base = max(3.0, 5.0 + structure * 8.0)  # 3~13天
        else:
            halflife_base = 7.0
        self.forgetting.halflife_base = halflife_base
        logger.info(f"[Memory] Forgetting halflife adjusted to {halflife_base:.1f}d (by personality: {self.personality.is_impact_enabled('memory_decay')})")

    async def initialize(self):
        self.long_term.initialize()
        self.graph.initialize()
        self.initialized = True
        self.forgetting.start()
        p = self.personality
        logger.info(f"[Memory] Initialized ({self.long_term.count()} memories)")
        logger.info(f"[SBTI] {p.type.emoji} {p.current_code} ({p.type.name})")

    async def store_interaction(self, session_id, role, content, importance=None):
        self.short_term.add(session_id, role, content)
        if content.strip():
            # ── 情绪分析 ──
            if role == "user":
                self.pad.update(content)
                self.pad.decay()
                self.pad.record_history()
            emotion = self.pad.get_emotional_state()

            # ── 重要性：人格影响 ──
            imp = importance if importance is not None else self._calc_importance(content, role, emotion)
            asyncio.create_task(self._store_long_term(content, imp, emotion))
            asyncio.create_task(self._store_graph(content))

    def _calc_importance(self, content, role, emotion=None):
        base = 0.5 + (0.1 if role == "user" else 0)
        lb = min(len(content) / 500, 0.3)
        kws = {"重要","记住","关键","配置","密码","名字","喜欢","讨厌","提醒","计划"}
        kb = min(sum(1 for kw in kws if kw in content) * 0.05, 0.2)
        base_imp = min(base + lb + kb, 1.0)

        # 人格影响（有开关控制）
        if self.personality.is_impact_enabled("importance_bias"):
            sysp = self.personality.get_impact()
            bias = sysp.get("emotional_depth", 0.5) * 0.3
            if emotion:
                mag = emotion.get("magnitude", 0)
                base_imp += mag * bias * 0.2
            base_imp += mag * bias * 0.2

        return min(base_imp, 1.0)

    async def _store_long_term(self, content, importance=0.5, emotion=None):
        try:
            emb = await self.embedding.embed(content)
            # 附带PAD情绪染色
            pad = emotion or {}
            mid = self.long_term.add(content, emb, importance=importance,
                                     pleasure=pad.get("pleasure", 0),
                                     arousal=pad.get("arousal", 0),
                                     dominance=pad.get("dominance", 0))
            logger.debug(f"[Memory] Stored #{mid} imp={importance:.2f}")
        except Exception as e:
            logger.error(f"[Memory] Store failed: {e}")

    async def _store_graph(self, content):
        try:
            words = self._extract_keywords(content)
            if len(words) >= 2:
                # 人格影响的Hebbian学习率（有开关控制）
                lr_mult = 1.0
                if self.personality.is_impact_enabled("hebbian_lr"):
                    sysp = self.personality.get_impact()
                    lr_mult = sysp.get("hebbian_lr_mult", 1.0)
                self.graph.relate_concepts(words, lr_mult=lr_mult)
        except Exception as e:
            logger.debug(f"[Memory] Graph: {e}")

    def _extract_keywords(self, text):
        words = re.findall(r'[\w\u4e00-\u9fff]+', text.lower())
        return [w for w in words if len(w) > 1 and w not in STOP_WORDS][:10]

    async def retrieve_context(self, session_id, query=None):
        q = query or ""
        ctx = {"short_term": [], "long_term": [], "graph": []}
        st = self.short_term.get_context(session_id)
        ctx["short_term"] = st[-10:] if len(st) > 10 else st
        if q.strip():
            try:
                qe = await self.embedding.embed(q)
                vr = self.long_term.search_vector(qe, top_k=10)
                kr = self.long_term.search_keyword(q, top_k=10)
                scored = {}
                for i, r in enumerate(vr): scored[r.id] = scored.get(r.id, 0) + 0.4/(i+60)
                for i, r in enumerate(kr): scored[r.id] = scored.get(r.id, 0) + 0.3/(i+60)
                for mid, sc in sorted(scored.items(), key=lambda x: -x[1])[:5]:
                    mem = self.long_term.get(mid)
                    if mem:
                        self.long_term.update_access(mid)
                        ctx["long_term"].append({"id": mem.id, "content": mem.content, "importance": mem.importance, "relevance": round(sc, 3)})
            except Exception as e:
                logger.error(f"[Memory] Retrieval: {e}")
        if q.strip():
            try:
                kws = self._extract_keywords(q)
                rel = set()
                for kw in kws:
                    for name, weight in self.graph.get_related(kw, top_k=3):
                        rel.add(name)
                ctx["graph"] = list(rel)[:5]
            except Exception as e:
                logger.debug(f"[Memory] Graph: {e}")
        return ctx

    def format_context(self, ctx):
        parts = []
        if ctx.get("graph"):
            parts.append("[相关概念] " + " \u00b7 ".join(ctx["graph"]))
        if ctx.get("long_term"):
            parts.append("[记忆回顾]\n" + "\n".join(f"- {m['content']} (相关度:{m.get('relevance','N/A')})" for m in ctx["long_term"]))
        if ctx.get("short_term"):
            lines = [f"{'用户' if m.get('role')=='user' else '助手'}: {m.get('content','')[:200]}" for m in ctx["short_term"]]
            parts.append("[对话历史]\n" + "\n".join(lines))
        return "\n\n".join(parts)

    async def close(self):
        self.forgetting.stop()
        await self.embedding.close()
