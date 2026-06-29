"""长期记忆 — SQLite + FTS5 + 向量检索 (sqlite-vec)"""
import sqlite3
import json
import time
import sqlite_vec
import numpy as np
from pathlib import Path
from typing import Optional
from dataclasses import dataclass


@dataclass
class MemoryItem:
    id: int
    content: str
    embedding: Optional[bytes] = None
    created_at: float = 0.0
    last_accessed: float = 0.0
    access_count: int = 1
    importance: float = 0.5
    tags: list[str] = None
    archived: bool = False
    pleasure: float = 0.0
    arousal: float = 0.0
    dominance: float = 0.0


class LongTermMemory:
    """长期记忆: SQLite + sqlite-vec + FTS5"""

    def __init__(self, db_path: str, embedding_dim: int = 384):
        self.db_path = db_path
        self.embedding_dim = embedding_dim
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn: Optional[sqlite3.Connection] = None

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path)
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def initialize(self):
        conn = self._get_conn()
        conn.enable_load_extension(True)  # required on Python 3.12+
        sqlite_vec.load(conn)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("""CREATE TABLE IF NOT EXISTS long_term_memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content TEXT NOT NULL,
            embedding BLOB,
            created_at REAL NOT NULL,
            last_accessed REAL NOT NULL,
            access_count INTEGER DEFAULT 1,
            importance REAL DEFAULT 0.5,
            tags TEXT DEFAULT '[]',
            archived INTEGER DEFAULT 0,
            pleasure REAL DEFAULT 0.0,
            arousal REAL DEFAULT 0.0,
            dominance REAL DEFAULT 0.0
        )""")
        conn.execute("""CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
            content, tags, content=long_term_memories, content_rowid=id
        )""")
        conn.execute(f"""CREATE VIRTUAL TABLE IF NOT EXISTS memories_vec USING vec0(
            id INTEGER PRIMARY KEY, embedding float[{self.embedding_dim}]
        )""")
        # FTS triggers
        conn.execute("""CREATE TRIGGER IF NOT EXISTS memories_ai AFTER INSERT ON long_term_memories BEGIN
            INSERT INTO memories_fts(rowid, content, tags) VALUES (new.id, new.content, new.tags); END;""")
        conn.execute("""CREATE TRIGGER IF NOT EXISTS memories_ad AFTER DELETE ON long_term_memories BEGIN
            INSERT INTO memories_fts(memories_fts, rowid, content, tags) VALUES ('delete', old.id, old.content, old.tags); END;""")
        conn.execute("""CREATE TRIGGER IF NOT EXISTS memories_au AFTER UPDATE ON long_term_memories BEGIN
            INSERT INTO memories_fts(memories_fts, rowid, content, tags) VALUES ('delete', old.id, old.content, old.tags);
            INSERT INTO memories_fts(rowid, content, tags) VALUES (new.id, new.content, new.tags); END;""")
        conn.commit()

    def add(self, content: str, embedding: np.ndarray, importance: float = 0.5, tags: list[str] = None,
            pleasure: float = 0.0, arousal: float = 0.0, dominance: float = 0.0) -> int:
        now = time.time()
        conn = self._get_conn()
        emb_bytes = embedding.astype(np.float32).tobytes()
        cur = conn.execute("""INSERT INTO long_term_memories (content,embedding,created_at,last_accessed,access_count,importance,tags,pleasure,arousal,dominance)
            VALUES (?,?,?,?,1,?,?,?,?,?)""",
            (content, emb_bytes, now, now, importance, json.dumps(tags or []), pleasure, arousal, dominance))
        mem_id = cur.lastrowid
        conn.execute("INSERT INTO memories_vec (id, embedding) VALUES (?, ?)", (mem_id, emb_bytes))
        conn.commit()
        return mem_id

    def search_vector(self, query_emb: np.ndarray, top_k: int = 10) -> list[MemoryItem]:
        conn = self._get_conn()
        qb = query_emb.astype(np.float32).tobytes()
        rows = conn.execute(f"""SELECT m.*, vec_distance_cosine(m.embedding, ?) AS distance
            FROM memories_vec v JOIN long_term_memories m ON m.id=v.id
            WHERE m.archived=0 ORDER BY distance ASC LIMIT ?""", (qb, top_k)).fetchall()
        return [self._row_to_item(r) for r in rows]

    def search_keyword(self, query: str, top_k: int = 10) -> list[MemoryItem]:
        conn = self._get_conn()
        rows = conn.execute("""SELECT m.*, rank AS bm25_score FROM memories_fts f
            JOIN long_term_memories m ON m.id=f.rowid
            WHERE memories_fts MATCH ? AND m.archived=0 ORDER BY rank LIMIT ?""", (query, top_k)).fetchall()
        return [self._row_to_item(r) for r in rows]

    def hybrid_search(self, query_emb: np.ndarray, query_text: str,
                       vw: float = 0.4, kw: float = 0.3, rw: float = 0.3,
                       knn_k: int = 10, fts_k: int = 10, final_k: int = 5) -> list[tuple[MemoryItem, float]]:
        from collections import defaultdict
        now = time.time()
        vr = self.search_vector(query_emb, knn_k)
        kr = self.search_keyword(query_text, fts_k)
        scores = defaultdict(float)
        items = {}
        for rank, item in enumerate(vr):
            scores[item.id] += vw / (rank + 60)
            items[item.id] = item
        for rank, item in enumerate(kr):
            scores[item.id] += kw / (rank + 60)
            items[item.id] = item
        for mid, item in items.items():
            days = (now - item.last_accessed) / 86400
            scores[mid] += rw * np.exp(-days / 7)
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:final_k]
        return [(items[mid], sc) for mid, sc in ranked]

    def get(self, mem_id: int) -> MemoryItem | None:
        """按 ID 获取单条记忆"""
        row = self._get_conn().execute(
            "SELECT * FROM long_term_memories WHERE id=? AND archived=0", (mem_id,)
        ).fetchone()
        return self._row_to_item(row) if row else None

    def update_access(self, mem_id: int):
        self._get_conn().execute("UPDATE long_term_memories SET last_accessed=?, access_count=access_count+1 WHERE id=?",
            (time.time(), mem_id)).connection.commit()

    def archive(self, mem_id: int):
        self._get_conn().execute("UPDATE long_term_memories SET archived=1 WHERE id=?", (mem_id,)).connection.commit()

    def archive_old(self, days: int = 90):
        self._get_conn().execute("UPDATE long_term_memories SET archived=1 WHERE last_accessed<?", (time.time()-days*86400,)).connection.commit()

    def get_all_active(self) -> list[MemoryItem]:
        rows = self._get_conn().execute("SELECT * FROM long_term_memories WHERE archived=0 ORDER BY last_accessed DESC").fetchall()
        return [self._row_to_item(r) for r in rows]

    def count(self) -> int:
        return self._get_conn().execute("SELECT COUNT(*) FROM long_term_memories WHERE archived=0").fetchone()[0]

    def _row_to_item(self, row) -> MemoryItem:
        return MemoryItem(id=row["id"], content=row["content"], created_at=row["created_at"],
            last_accessed=row["last_accessed"], access_count=row["access_count"],
            importance=row["importance"], tags=json.loads(row["tags"] or "[]"), archived=bool(row["archived"]),
            pleasure=row["pleasure"] if "pleasure" in row.keys() else 0.0,
            arousal=row["arousal"] if "arousal" in row.keys() else 0.0,
            dominance=row["dominance"] if "dominance" in row.keys() else 0.0)

    def close(self):
        if self._conn: self._conn.close(); self._conn = None