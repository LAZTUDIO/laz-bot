"""Embedding client - reads active model from config each call"""
import numpy as np, os, yaml, httpx
from typing import Optional

CONFIG_PATH = os.environ.get("LAZ_CONFIG", os.path.join(os.path.dirname(__file__), "..", "config.yaml"))

def _load():
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH) as f:
            return yaml.safe_load(f) or {}
    return {}

class EmbeddingClient:
    def __init__(self):
        self._client = None

    async def _get_client(self):
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client

    def _get_active_entry(self):
        cfg = _load()
        ec = cfg.get("models", {}).get("embedding", {})
        active = ec.get("active", "")
        for e in ec.get("entries", []):
            if e.get("name") == active:
                return e
        entries = ec.get("entries", [])
        return entries[0] if entries else None

    def get_dim(self):
        e = self._get_active_entry()
        return e.get("dim", 384) if e else 384

    async def embed(self, text):
        r = await self.embed_batch([text])
        return r[0]

    async def embed_batch(self, texts):
        entry = self._get_active_entry()
        if not entry:
            raise RuntimeError("No embedding model configured")
        url = entry.get("base_url", "").rstrip("/") + "/embeddings"
        model = entry.get("model_id", "")
        key = entry.get("api_key", "")
        headers = {"Content-Type": "application/json"}
        if key:
            headers["Authorization"] = f"Bearer {key}"
        try:
            client = await self._get_client()
            r = await client.post(url, json={"model": model, "input": texts}, headers=headers)
            r.raise_for_status()
            data = r.json()
            return [np.array(d["embedding"], dtype=np.float32) for d in data["data"]]
        except Exception as e:
            print(f"[Embedding] Failed: {e}")
            dim = self.get_dim()
            return [np.zeros(dim, dtype=np.float32)] * len(texts)

    async def close(self):
        if self._client:
            await self._client.aclose()
