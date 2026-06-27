"""ALSA 直接采集 — 用 arecord 子进程，绕过 PortAudio/PulseAudio"""
import asyncio
import subprocess
import numpy as np
import logging

logger = logging.getLogger("laz-bot.alsa")


class AlsaCapture:
    """ALSA 录音器: arecord → 管道 → numpy 帧流"""

    def __init__(self, device: str = "plughw:2,0", sample_rate: int = 48000,
                 channels: int = 1, frame_size: int = 1024):
        self.device = device
        self.sample_rate = sample_rate
        self.channels = channels
        self.frame_size = frame_size
        self._proc: subprocess.Popen | None = None

    def start(self):
        """启动 arecord 子进程"""
        bytes_per_frame = self.frame_size * 2  # S16_LE = 2 bytes/sample
        cmd = [
            "arecord",
            "-D", self.device,
            "-f", "S16_LE",
            "-r", str(self.sample_rate),
            "-c", str(self.channels),
            "-t", "raw",
            "--buffer-size", str(bytes_per_frame * 4),
            "-q",
            "-",
        ]
        logger.info(f"[ALSA] Starting: {' '.join(cmd)}")
        self._proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            bufsize=0,
        )

    def read(self) -> np.ndarray:
        """读取一帧，返回 float32 [-1,1]"""
        if self._proc is None:
            raise RuntimeError("ALSA capture not started")
        data = self._proc.stdout.read(self.frame_size * 2)
        if not data or len(data) < self.frame_size * 2:
            return np.zeros(self.frame_size, dtype=np.float32)
        return np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0

    def stop(self):
        if self._proc:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self._proc.kill()
            self._proc = None


class AlsaPlayback:
    """ALSA 播放器: aplay 子进程"""

    def __init__(self, device: str = "plughw:2,0", sample_rate: int = 48000,
                 channels: int = 1):
        self.device = device
        self.sample_rate = sample_rate
        self.channels = channels
        self._proc: subprocess.Popen | None = None

    def start(self):
        cmd = [
            "aplay",
            "-D", self.device,
            "-f", "S16_LE",
            "-r", str(self.sample_rate),
            "-c", str(self.channels),
            "-t", "raw",
            "-q",
            "-",
        ]
        logger.info(f"[ALSA] Playback: {' '.join(cmd)}")
        self._proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            bufsize=0,
        )

    def write(self, audio: np.ndarray):
        """写入 float32 音频帧"""
        if self._proc is None or self._proc.poll() is not None:
            return
        audio_int16 = np.clip(audio * 32767, -32768, 32767).astype(np.int16)
        try:
            self._proc.stdin.write(audio_int16.tobytes())
            self._proc.stdin.flush()
        except BrokenPipeError:
            pass

    def stop(self):
        if self._proc:
            try:
                self._proc.stdin.close()
            except Exception:
                pass
            self._proc.terminate()
            try:
                self._proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self._proc.kill()
            self._proc = None
