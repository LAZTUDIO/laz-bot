"""TTS 客户端 — 硅基流动语音合成 (MOSS-TTSD)"""
import httpx
import subprocess
import tempfile
import numpy as np
import logging
from typing import Optional

logger = logging.getLogger("laz-bot.tts")


class TTSClient:
    """文本转语音客户端 (硅基流动 /audio/speech API)"""

    def __init__(self, api_key: str, base_url: str = "https://api.siliconflow.cn/v1",
                 model: str = "fnlp/MOSS-TTSD-v0.5",
                 voice: str = "fnlp/MOSS-TTSD-v0.5:alex",
                 speed: float = 1.0,
                 response_format: str = "mp3"):
        self.api_key = api_key
        self.base_url = base_url
        self.model = model
        self.voice = voice
        self.speed = speed
        self.response_format = response_format
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=60.0)
        return self._client

    async def synthesize(self, text: str) -> Optional[np.ndarray]:
        """
        合成语音，返回 float32 numpy array (48kHz mono)
        """
        client = await self._get_client()
        try:
            response = await client.post(
                f"{self.base_url}/audio/speech",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": self.model,
                    "input": text,
                    "voice": self.voice,
                    "response_format": self.response_format,
                    "speed": self.speed,
                },
            )

            if response.status_code != 200:
                logger.error(f"[TTS] HTTP {response.status_code}: {response.text[:200]}")
                return None

            # 解码: MP3/WAV → PCM
            suffix = ".mp3" if self.response_format == "mp3" else ".wav"
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmpf:
                tmpf.write(response.content)
                tmp_path = tmpf.name

            try:
                if self.response_format == "wav":
                    # WAV → PCM via ffmpeg (handles any sample rate)
                    proc = subprocess.run(
                        ["ffmpeg", "-y", "-i", tmp_path, "-f", "s16le",
                         "-ar", "48000", "-ac", "1", "-"],
                        capture_output=True, timeout=15,
                    )
                else:
                    # MP3 → PCM
                    proc = subprocess.run(
                        ["ffmpeg", "-y", "-i", tmp_path, "-f", "s16le",
                         "-ar", "48000", "-ac", "1", "-"],
                        capture_output=True, timeout=15,
                    )

                if proc.returncode != 0:
                    logger.error(f"[TTS] ffmpeg failed: {proc.stderr.decode()[:200]}")
                    return None

                pcm = np.frombuffer(proc.stdout, dtype=np.int16).astype(np.float32) / 32768.0
                logger.info(f"[TTS] Synthesized {len(pcm)} samples ({len(pcm)/48000:.1f}s, fmt={self.response_format})")
                return pcm

            finally:
                import os
                try:
                    os.unlink(mp3_path)
                except Exception:
                    pass

        except Exception as e:
            logger.error(f"[TTS] Request failed: {e}")
            return None

    async def close(self):
        if self._client:
            await self._client.aclose()
