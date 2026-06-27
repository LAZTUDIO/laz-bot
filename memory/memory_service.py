"""Unified memory service"""
import asyncio, re, logging, os
from .short_term import ShortTermMemory
from .long_term import LongTermMemory
from .episodic_graph import EpisodicGraph
from .forgetting import ForgettingScheduler
from .embedding_client import EmbeddingClient

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
        fc = mc.get("forgetting", {})
        self.forgetting = ForgettingScheduler(
            long_term_memory=self.long_term,
            episodic_graph=self.graph,
            halflife_base=fc.get("halflife_base", 7),
            archive_threshold=fc.get("archive_threshold", 0.05),
            cleanup_after_days=fc.get("cleanup_after_days", 90))
        self.initialized = False

    async def initialize(self):
        self.long_term.initialize()
        self.graph.initialize()
        self.initialized = True
        self.forgetting.start()
        logger.info(f"[Memory] Initialized ({self.long_term.count()} memories)")

    async def store_interaction(self, session_id, role, content, importance=None):
        self.short_term.add(session_id, role, content)
        if content.strip():
            imp = importance if importance is not None else self._calc_importance(content, role)
            asyncio.create_task(self._store_long_term(content, imp))
            asyncio.create_task(self._store_graph(content))

    def _calc_importance(self, content, role):
        base = 0.5 + (0.1 if role == "user" else 0)
        lb = min(len(content) / 500, 0.3)
        kws = {"重要","记住","关键","配置","密码","名字","喜欢","讨厌","提醒","计划"}
        kb = min(sum(1 for kw in kws if kw in content) * 0.05, 0.2)
        return min(base + lb + kb, 1.0)

    async def _store_long_term(self, content, importance=0.5):
        try:
            emb = await self.embedding.embed(content)
            mid = self.long_term.add(content, emb, importance=importance)
            logger.debug(f"[Memory] Stored #{mid}")
        except Exception as e:
            logger.error(f"[Memory] Store failed: {e}")

    async def _store_graph(self, content):
        try:
            words = self._extract_keywords(content)
            if len(words) >= 2:
                self.graph.relate_concepts(words)
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
