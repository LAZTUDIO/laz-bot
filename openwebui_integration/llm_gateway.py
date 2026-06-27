"""LLM Provider — 实时读取 config 活跃模型条目，直调 OpenAI 兼容 API"""
import httpx
import yaml
import os
from typing import Optional

CONFIG_PATH = os.environ.get("LAZ_CONFIG", os.path.join(os.path.dirname(__file__), "..", "config.yaml"))

def _load_config():
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}

def _get_active_llm_entry():
    """从 config 读取当前活跃的 LLM 模型条目。"""
    cfg = _load_config()
    models = cfg.get("models", {})
    llm_cfg = models.get("llm", {})
    active_name = llm_cfg.get("active", "")
    entries = llm_cfg.get("entries", [])
    for e in entries:
        if e.get("name") == active_name:
            return e
    # fallback: 取第一个条目
    return entries[0] if entries else None


class LLMProvider:
    """
    实时从 config.yaml 读取活跃 LLM 模型条目，
    直调 OpenAI 兼容的 chat/completions 接口。
    不依赖 Open WebUI，不存储全局 api_key。
    """

    def __init__(self):
        # 不预存任何凭据，每次调用实时读 config
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=120.0)
        return self._client

    async def chat_completion(self, messages: list[dict],
                              temperature: float = 0.7,
                              max_tokens: int = 4096,
                              stream: bool = False) -> dict:
        """调用活跃 LLM 模型进行对话补全。"""
        entry = _get_active_llm_entry()
        if not entry:
            return {
                "choices": [{
                    "message": {
                        "role": "assistant",
                        "content": "[错误] 未配置 LLM 模型，请先在管理界面添加并激活一个 LLM 模型。"
                    }
                }]
            }

        base_url = entry.get("base_url", "").rstrip("/")
        model_id = entry.get("model_id", "")
        api_key = entry.get("api_key", "")

        if not base_url or not model_id:
            return {
                "choices": [{
                    "message": {
                        "role": "assistant",
                        "content": f"[错误] LLM 模型「{entry.get('name', 'unknown')}」配置不完整，缺少 base_url 或 model_id。"
                    }
                }]
            }

        url = f"{base_url}/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        } if api_key else {
            "Content-Type": "application/json"
        }

        payload = {
            "model": model_id,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": stream
        }

        client = await self._get_client()
        try:
            resp = await client.post(url, json=payload, headers=headers)
            if resp.status_code == 401:
                return {
                    "choices": [{
                        "message": {
                            "role": "assistant",
                            "content": f"[错误] API 认证失败 (HTTP 401)，请检查「{entry.get('name', '')}」的 API 密钥。"
                        }
                    }]
                }
            resp.raise_for_status()
            return resp.json()
        except httpx.TimeoutException:
            return {
                "choices": [{
                    "message": {
                        "role": "assistant",
                        "content": f"[错误] 请求超时，请检查「{entry.get('name', '')}」的 base_url 是否正确或网络是否可达。"
                    }
                }]
            }
        except Exception as e:
            return {
                "choices": [{
                    "message": {
                        "role": "assistant",
                        "content": f"[错误] LLM 调用失败: {str(e)[:200]}"
                    }
                }]
            }

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None
