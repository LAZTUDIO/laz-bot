"""LLM Router - reads active LLM entry live"""
import httpx
from typing import Optional

class LLMRouter:
    def __init__(self, config: dict, model_router):
        self._config = config
        self._mr = model_router
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=120.0)
        return self._client

    async def chat_completion(self, messages, model=None, tools=None, **kw):
        entry = self._mr.get_active_llm()
        if not entry:
            return {"error": "No active LLM configured"}
        base_url = entry.get("base_url", "").rstrip("/")
        model_id = model or entry.get("model_id", "")
        api_key = entry.get("api_key", "")
        timeout = entry.get("timeout", 120)
        if not base_url or not model_id:
            return {"error": "LLM config incomplete"}
        client = await self._get_client()
        payload = {"model": model_id, "messages": messages, "stream": False}
        if tools:
            payload["tools"] = tools
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        print(f"[LLMRouter] Calling {base_url}/chat/completions model={model_id}")
        try:
            resp = await client.post(f"{base_url}/chat/completions", json=payload, headers=headers, timeout=timeout)
            if resp.status_code == 200:
                return resp.json()
            return {"error": f"HTTP {resp.status_code}: {resp.text[:300]}"}
        except Exception as e:
            return {"error": str(e)}

    async def close(self):
        if self._client:
            await self._client.aclose()
