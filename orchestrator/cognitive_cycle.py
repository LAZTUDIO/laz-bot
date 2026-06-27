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
        session = self.sessions.get_or_create(session_id)
        session.add_message("user", text)
        memory_ctx = await self._attend(text, session_id)
        llm_response = await self._think(text, memory_ctx, session_id)
        if "error" in llm_response:
            session.add_message("assistant", text[:50])
            return text[:50]
        message = llm_response["choices"][0]["message"]
        if message.get("tool_calls"):
            final = await self._act(message, session_id)
        else:
            final = message.get("content", "")
        asyncio.create_task(self._reflect(session_id, text, final))
        if isinstance(final, str):
            session.add_message("assistant", final)
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
        if self.memory:
            msgs.extend(self.memory.short_term.get_chat_messages(session_id, 10))
        if not msgs or msgs[-1]["role"] != "user":
            msgs.append({"role": "user", "content": text})
        tools = self.executor.get_tool_definitions() if self.executor else None
        if self.llm:
            return await self.llm.chat_completion(messages=msgs, tools=tools)
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
        lines = [
            "你是 LAZ-Bot，运行在树莓派 5 上的本地编排融合智能体。",
            "你拥有语音交互、记忆系统和工具调用能力。",
            "回答要简洁、准确、有帮助。",
        ]
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
