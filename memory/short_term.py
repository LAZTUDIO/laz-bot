"""短期记忆 — 工作记忆 (deque, 最近 50 轮)"""
from collections import deque
from dataclasses import dataclass, field
import time


@dataclass
class STMessage:
    """短期记忆中的单条消息"""
    role: str          # "user" | "assistant" | "system" | "tool"
    content: str
    session_id: str
    timestamp: float = field(default_factory=time.time)


class ShortTermMemory:
    """
    短期记忆 (工作记忆)
    存储最近 N 轮对话，不持久化
    """

    def __init__(self, max_rounds: int = 50):
        self.max_rounds = max_rounds
        self._sessions: dict[str, deque[STMessage]] = {}

    def _get_buffer(self, session_id: str) -> deque:
        if session_id not in self._sessions:
            self._sessions[session_id] = deque(maxlen=self.max_rounds)
        return self._sessions[session_id]

    def add(self, session_id: str, role: str, content: str):
        """添加一条消息到短期记忆"""
        buf = self._get_buffer(session_id)
        buf.append(STMessage(role=role, content=content, session_id=session_id))

    def get_context(self, session_id: str, max_messages: int = 50) -> list[dict]:
        """获取最近的对话消息 (用于拼入 prompt)"""
        buf = self._sessions.get(session_id)
        if not buf:
            return []
        recent = list(buf)[-max_messages:]
        return [
            {"role": m.role, "content": m.content, "timestamp": m.timestamp}
            for m in recent
        ]

    def get_chat_messages(self, session_id: str, max_messages: int = 50) -> list[dict]:
        """获取 OpenAI 格式的消息列表"""
        buf = self._sessions.get(session_id)
        if not buf:
            return []
        recent = list(buf)[-max_messages:]
        return [{"role": m.role, "content": m.content} for m in recent
                if m.role in ("user", "assistant", "system")]

    def clear(self, session_id: str):
        """清空指定会话的短期记忆"""
        self._sessions.pop(session_id, None)

    def clear_all(self):
        """清空所有短期记忆"""
        self._sessions.clear()

    def count(self, session_id: str) -> int:
        """获取指定会话的消息数量"""
        buf = self._sessions.get(session_id)
        return len(buf) if buf else 0