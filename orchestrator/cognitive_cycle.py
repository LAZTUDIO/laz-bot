"""Cognitive Cycle: Perceive -> Attend -> Think -> Act -> Reflect"""
import asyncio, uuid, logging
from .session_manager import SessionManager

logger = logging.getLogger("laz-bot.cognitive")

class CognitiveCycle:
    def __init__(self, config, memory_service=None, llm_router=None, executor=None):
        self.config = config
        self.memory = memory_service
        self.llm = llm_router
        self.executor = executor
        self.sessions = SessionManager()
        self.running = True

    async def process_text(self, text, session_id=None):
        if not session_id:
            session_id = str(uuid.uuid4())
        self.sessions.add_message(session_id, "user", text)
        session = self.sessions.get(session_id)
        memory_ctx = await self._attend(text, session_id)
        llm_response = await self._think(text, memory_ctx, session_id)
        if "error" in llm_response:
            self.sessions.add_message(session_id, "assistant", text[:50])
            return text[:50]
        message = llm_response["choices"][0]["message"]
        if message.get("tool_calls"):
            final = await self._act(message, session_id)
        else:
            final = message.get("content", "")
        asyncio.create_task(self._reflect(session_id, text, final))
        if isinstance(final, str):
            self.sessions.add_message(session_id, "assistant", final)
        return final

    async def _attend(self, query, session_id):
        parts = []
        if self.memory and self.memory.initialized:
            try:
                ctx = await self.memory.retrieve_context(session_id, query)
                mt = self.memory.format_context(ctx)
                if mt:
                    parts.append(mt)
            except Exception as e:
                logger.error(f"[Attend] {e}")
        return {"context": "\n".join(parts)}

    async def _think(self, text, memory_ctx, session_id):
        sp = self._build_system_prompt(memory_ctx)
        msgs = [{"role": "system", "content": sp}]
        prelude = ""
        if self.memory:
            # 注入当前情绪（PAD影响，有pad_baseline开关）
            emotion = self.memory.pad.get_emotional_state()
            if emotion.get("label") != "平静":
                prelude = f"[情绪: {emotion['label']} P={emotion['pleasure']:.1f} A={emotion['arousal']:.1f} D={emotion['dominance']:.1f}] "
            msgs.extend(self.memory.short_term.get_chat_messages(session_id, 10))

            # 人格影响回复长度（有开关控制）
            if self.memory.personality.is_impact_enabled("reply_length"):
                sysp = self.memory.personality.get_impact()
                verbosity = sysp.get("verbosity", 0.5)
                max_tokens = int(196 + verbosity * 600)
            else:
                max_tokens = 512
        else:
            max_tokens = 512

        if not msgs or msgs[-1]["role"] != "user":
            msgs.append({"role": "user", "content": prelude + text})

        tools = self.executor.get_tool_definitions() if self.executor else None
        if self.llm:
            return await self.llm.chat_completion(messages=msgs, tools=tools, max_tokens=max_tokens)
        return {"choices": [{"message": {"content": f"[Fallback] {text[:50]}..."}}]}

    async def _act(self, message, session_id):
        if not self.executor:
            return message.get("content", "")
        tool_calls = message["tool_calls"]
        session = self.sessions.get(session_id)
        if message.get("content"):
            session.add_message("assistant", message["content"])
        for _ in range(self.executor.max_rounds):
            results = await self.executor.execute_tool_calls(tool_calls)
            msgs = [{"role": "system", "content": self._build_system_prompt({"context": ""})}]
            msgs.extend(self.memory.short_term.get_chat_messages(session_id, 10))
            msgs.append(message)
            msgs.extend(results)
            r = await self.llm.chat_completion(messages=msgs, tools=self.executor.get_tool_definitions())
            if "error" in r:
                break
            nm = r["choices"][0]["message"]
            if nm.get("tool_calls"):
                tool_calls = nm["tool_calls"]
                message = nm
                continue
            return nm.get("content", "")
        return message.get("content", "")

    async def _reflect(self, session_id, user_input, response):
        if not self.memory or not self.memory.initialized:
            return
        try:
            await self.memory.store_interaction(session_id, "user", user_input)
            if response:
                await self.memory.store_interaction(session_id, "assistant", str(response))
        except Exception as e:
            logger.error(f"[Reflect] {e}")

    def _build_system_prompt(self, memory_ctx):
        # 人格注入（有开关控制）
        pers_block = ""
        warmth_notes = ""
        if self.memory:
            p = self.memory.personality
            if p.is_impact_enabled("llm_prompt"):
                sbtype = p.type
                pers_block = f"你当前的人格是「{sbtype.emoji} {sbtype.name}」({sbtype.code})。\n"
                pers_block += f"{sbtype.description}\n"
                pers_block += f"特质: {sbtype.features}\n\n"
            if p.is_impact_enabled("warmth_tone"):
                sysp = p.get_impact()
                warmth = sysp.get("warmth", 0.5)
                trust = sysp.get("trust_assumption", 0.5)
                direct = sysp.get("directness", 0.5)
                if warmth > 0.7:
                    warmth_notes = "语气要温暖、共情、像朋友一样。"
                elif warmth < 0.3:
                    warmth_notes = "语气要冷静、客观、保持距离。"
                if trust < 0.4:
                    warmth_notes += "对用户说的信息保持适度怀疑，可以追问确认。"
                if direct > 0.7:
                    warmth_notes += "表达要直接，不用绕弯子。"
        lines = [pers_block + "你是 LAZ-Bot，运行在树莓派上的融合智能体。"]
        if self.memory:
            emotion = self.memory.pad.get_emotional_state()
            lines.append(f"用户当前情绪状态: {emotion['label']} "
                         f"(愉悦={emotion['pleasure']:.2f} 唤醒={emotion['arousal']:.2f} 支配={emotion['dominance']:.2f})")
        lines.append(warmth_notes)
        lines.extend([
            "你拥有语音交互、记忆系统和工具调用能力。",
        ])
        ctx = memory_ctx.get("context", "")
        if ctx:
            lines.append("\n=== 上下文信息 ===")
            lines.append(ctx)
        return "\n".join(lines)

    def get_session_summary(self, session_id: str):
        session = self.sessions.get(session_id)
        if not session:
            return {"error": "Session not found"}
        return {
            "id": session.id,
            "messages": [{"role": m.role, "content": m.content, "timestamp": m.timestamp}
                         for m in session.messages],
            "created_at": session.created_at,
            "last_active": session.last_active,
        }

    async def shutdown(self):
        self.running = False
        if self.memory:
            await self.memory.close()
        if self.llm:
            await self.llm.close()
