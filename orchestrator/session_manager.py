"""会话管理器 — 追踪对话状态，自动持久化到 JSON 文件"""
import json
import os
import time
from collections import deque
from dataclasses import dataclass, field, asdict
from typing import List, Optional
import logging

logger = logging.getLogger("laz-bot.session")

CHAT_DB_PATH = os.environ.get("LAZ_CHAT_DB", os.path.join(os.path.dirname(__file__), "..", "data", "chat_sessions.json"))


@dataclass
class Message:
    role: str  # "user" | "assistant" | "system" | "tool"
    content: str
    timestamp: float = field(default_factory=time.time)


@dataclass
class Session:
    id: str
    title: str = "新对话"
    messages: List[Message] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    last_active: float = field(default_factory=time.time)

    def add_message(self, role: str, content: str):
        self.messages.append(Message(role=role, content=content))
        self.last_active = time.time()
        # Auto-title from first user message
        if role == "user" and self.title == "新对话":
            self.title = content[:48] + ("..." if len(content) > 48 else "")

    def get_recent(self, n: int = 10) -> List[Message]:
        return self.messages[-n:]

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "msg_count": len(self.messages),
            "created_at": self.created_at,
            "last_active": self.last_active,
        }

    def to_full_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "messages": [{"role": m.role, "content": m.content, "timestamp": m.timestamp} for m in self.messages],
            "created_at": self.created_at,
            "last_active": self.last_active,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Session":
        s = cls(id=d["id"], title=d.get("title", "新对话"),
                created_at=d.get("created_at", time.time()),
                last_active=d.get("last_active", time.time()))
        for m in d.get("messages", []):
            s.messages.append(Message(role=m["role"], content=m["content"],
                                       timestamp=m.get("timestamp", time.time())))
        return s


class SessionManager:
    """管理多个对话会话，自动持久化到 JSON"""

    def __init__(self, max_sessions: int = 1000, db_path: str = CHAT_DB_PATH):
        self.sessions: dict[str, Session] = {}
        self.max_sessions = max_sessions
        self.db_path = db_path
        self._dirty = False
        self._load()

    def get_or_create(self, session_id: str) -> Session:
        if session_id not in self.sessions:
            self.sessions[session_id] = Session(id=session_id)
            self._dirty = True
            self._cleanup()
        return self.sessions[session_id]

    def get(self, session_id: str) -> Session | None:
        return self.sessions.get(session_id)

    def delete(self, session_id: str):
        if session_id in self.sessions:
            del self.sessions[session_id]
            self._dirty = True
            self._save()

    def rename(self, session_id: str, new_title: str):
        if session_id in self.sessions:
            self.sessions[session_id].title = new_title
            self._dirty = True
            self._save()

    def list_sessions(self) -> list:
        sessions = [s.to_dict() for s in self.sessions.values()]
        sessions.sort(key=lambda s: s["last_active"], reverse=True)
        return sessions

    def add_message(self, session_id: str, role: str, content: str):
        s = self.get_or_create(session_id)
        s.add_message(role, content)
        self._dirty = True
        self._save()

    def _cleanup(self):
        if len(self.sessions) > self.max_sessions:
            sorted_sessions = sorted(
                self.sessions.values(),
                key=lambda s: s.last_active
            )
            for s in sorted_sessions[:len(sorted_sessions) - self.max_sessions]:
                del self.sessions[s.id]
            self._dirty = True

    def _load(self):
        try:
            if os.path.exists(self.db_path):
                with open(self.db_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for item in data:
                    s = Session.from_dict(item)
                    self.sessions[s.id] = s
                logger.info(f"[Session] Loaded {len(self.sessions)} sessions from {self.db_path}")
        except Exception as e:
            logger.warning(f"[Session] Failed to load sessions: {e}")

    def _save(self):
        try:
            os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
            data = [s.to_full_dict() for s in self.sessions.values()]
            with open(self.db_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            self._dirty = False
        except Exception as e:
            logger.warning(f"[Session] Failed to save sessions: {e}")
