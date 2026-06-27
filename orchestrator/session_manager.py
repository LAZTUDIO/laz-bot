"""会话管理器 — 追踪对话状态"""
import time
from collections import deque
from dataclasses import dataclass, field
from typing import List


@dataclass
class Message:
    role: str  # "user" | "assistant" | "system" | "tool"
    content: str
    timestamp: float = field(default_factory=time.time)


@dataclass
class Session:
    id: str
    messages: List[Message] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    last_active: float = field(default_factory=time.time)
    
    def add_message(self, role: str, content: str):
        self.messages.append(Message(role=role, content=content))
        self.last_active = time.time()
    
    def get_recent(self, n: int = 10) -> List[Message]:
        return self.messages[-n:]
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "msg_count": len(self.messages),
            "created_at": self.created_at,
            "last_active": self.last_active,
        }


class SessionManager:
    """管理多个对话会话"""
    
    def __init__(self, max_sessions: int = 100):
        self.sessions: dict[str, Session] = {}
        self.max_sessions = max_sessions
    
    def get_or_create(self, session_id: str) -> Session:
        if session_id not in self.sessions:
            self.sessions[session_id] = Session(id=session_id)
            self._cleanup()
        return self.sessions[session_id]
    
    def get(self, session_id: str) -> Session | None:
        return self.sessions.get(session_id)
    
    def delete(self, session_id: str):
        self.sessions.pop(session_id, None)
    
    def list_sessions(self) -> list:
        return [s.to_dict() for s in self.sessions.values()]
    
    def _cleanup(self):
        """淘汰最旧的会话"""
        if len(self.sessions) > self.max_sessions:
            sorted_sessions = sorted(
                self.sessions.values(), 
                key=lambda s: s.last_active
            )
            for s in sorted_sessions[:len(sorted_sessions) - self.max_sessions]:
                self.delete(s.id)
