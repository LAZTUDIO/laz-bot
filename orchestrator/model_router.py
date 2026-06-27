"""Model router - reads config live"""
import os, yaml

CONFIG_PATH = os.environ.get("LAZ_CONFIG", os.path.join(os.path.dirname(__file__), "..", "config.yaml"))

def _load():
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH) as f:
            return yaml.safe_load(f) or {}
    return {}

class ModelRouter:
    def __init__(self, config=None):
        self._config = config or _load()
    def _reload(self):
        self._config = _load()
    def get_active_entry(self, cat):
        self._reload()
        cfg = self._config.get("models", {}).get(cat, {})
        active = cfg.get("active", "")
        for e in cfg.get("entries", []):
            if e.get("name") == active:
                return e
        entries = cfg.get("entries", [])
        return entries[0] if entries else None
    def get_active_llm(self):
        return self.get_active_entry("llm")
    def get_active_embedding(self):
        return self.get_active_entry("embedding")
