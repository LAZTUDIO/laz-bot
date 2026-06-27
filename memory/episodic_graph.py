"""情节记忆 (脑图) — 概念/事件图 + Hebbian 学习"""
import sqlite3
import time
from pathlib import Path
from typing import Optional


class EpisodicGraph:
    """概念/事件图 + Hebbian 学习"""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._conn: Optional[sqlite3.Connection] = None

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path)
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def initialize(self):
        conn = self._get_conn()
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("""CREATE TABLE IF NOT EXISTS concept_nodes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            node_type TEXT DEFAULT 'concept',
            created_at REAL NOT NULL,
            last_activated REAL NOT NULL,
            activation_count INTEGER DEFAULT 1
        )""")
        conn.execute("""CREATE TABLE IF NOT EXISTS concept_edges (
            source_id INTEGER NOT NULL,
            target_id INTEGER NOT NULL,
            weight REAL DEFAULT 1.0,
            co_occurrences INTEGER DEFAULT 1,
            PRIMARY KEY (source_id, target_id),
            FOREIGN KEY (source_id) REFERENCES concept_nodes(id),
            FOREIGN KEY (target_id) REFERENCES concept_nodes(id)
        )""")
        conn.commit()

    def _get_or_create_node(self, name: str, node_type: str = "concept") -> int:
        conn = self._get_conn()
        now = time.time()
        row = conn.execute("SELECT id FROM concept_nodes WHERE name=?", (name,)).fetchone()
        if row:
            conn.execute("UPDATE concept_nodes SET last_activated=?, activation_count=activation_count+1 WHERE id=?", (now, row["id"]))
            conn.commit()
            return row["id"]
        cur = conn.execute("INSERT INTO concept_nodes (name,node_type,created_at,last_activated) VALUES (?,?,?,?)", (name, node_type, now, now))
        conn.commit()
        return cur.lastrowid

    def relate_concepts(self, concepts: list[str]):
        if len(concepts) < 2: return
        node_ids = [self._get_or_create_node(c) for c in concepts]
        conn = self._get_conn()
        for i in range(len(node_ids)):
            for j in range(i+1, len(node_ids)):
                src, tgt = node_ids[i], node_ids[j]
                row = conn.execute("SELECT weight FROM concept_edges WHERE source_id=? AND target_id=?", (src, tgt)).fetchone()
                if row:
                    conn.execute("UPDATE concept_edges SET weight=MIN(weight+0.1,10.0), co_occurrences=co_occurrences+1 WHERE source_id=? AND target_id=?", (src, tgt))
                else:
                    conn.execute("INSERT INTO concept_edges (source_id,target_id,weight,co_occurrences) VALUES (?,?,0.3,1)", (src, tgt))
        conn.commit()

    def get_related(self, concept_name: str, top_k: int = 5) -> list[tuple[str, float]]:
        conn = self._get_conn()
        node = conn.execute("SELECT id FROM concept_nodes WHERE name=?", (concept_name,)).fetchone()
        if not node: return []
        nid = node["id"]
        rows = conn.execute("""SELECT n.name, e.weight FROM concept_edges e
            JOIN concept_nodes n ON n.id = CASE WHEN e.source_id=? THEN e.target_id ELSE e.source_id END
            WHERE e.source_id=? OR e.target_id=? ORDER BY e.weight DESC LIMIT ?""", (nid, nid, nid, top_k)).fetchall()
        return [(r["name"], r["weight"]) for r in rows]

    def get_context_from_text(self, text: str, top_k: int = 3) -> str:
        conn = self._get_conn()
        all_nodes = conn.execute("SELECT name FROM concept_nodes").fetchall()
        matched = [n["name"] for n in all_nodes if n["name"] in text]
        if not matched: return ""
        related = set()
        for m in matched[:3]:
            for name, w in self.get_related(m, 3):
                if w > 0.2: related.add(name)
        if not related: return ""
        return f"[脑图] 当前话题相关知识: {'、'.join(sorted(related))}"

    def decay_edges(self, threshold: float = 0.1):
        self._get_conn().execute("DELETE FROM concept_edges WHERE weight < ?", (threshold,)).connection.commit()

    def get_stats(self) -> dict:
        conn = self._get_conn()
        return {"nodes": conn.execute("SELECT COUNT(*) FROM concept_nodes").fetchone()[0],
                "edges": conn.execute("SELECT COUNT(*) FROM concept_edges").fetchone()[0]}

    def close(self):
        if self._conn: self._conn.close(); self._conn = None