"""STT 客户端 — 硅基流动语音识别"""
import httpx
import numpy as np
import soundfile as sf
from io import BytesIO
from typing import Optional


class STTClient:
    """
    语音转文本客户端 (硅基流动 API)
    兼容 OpenAI Whisper API 格式
    """
    
    def __init__(self, api_key: str, base_url: str = "https://api.siliconflow.cn/v1",
                 model: str = "FunAudioLLM/SenseVoiceSmall"):
        self.api_key = api_key
        self.base_url = base_url
        self.model = model
        self._client: Optional[httpx.AsyncClient] = None
    
    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client
    
    async def transcribe(self, audio: np.ndarray, sample_rate: int = 16000) -> str:
        """
        转录音频为文本
        audio: float32 numpy array, 值域 [-1, 1]
        返回: 识别文本
        """
        # Convert to WAV bytes
        wav_buffer = BytesIO()
        sf.write(wav_buffer, audio, sample_rate, format='WAV')
        wav_buffer.seek(0)
        
        client = await self._get_client()
        
        try:
            response = await client.post(
                f"{self.base_url}/audio/transcriptions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                files={
                    "file": ("audio.wav", wav_buffer, "audio/wav"),
                    "model": (None, self.model),
                    "language": (None, "zh"),
                }
            )
            
            if response.status_code == 200:
                result = response.json()
                return result.get("text", "")
            else:
                print(f"[STT] Error {response.status_code}: {response.text}")
                return ""
                
        except Exception as e:
            print(f"[STT] Request failed: {e}")
            return ""
    
    async def close(self):
        if self._client:
            await self._client.aclose()
