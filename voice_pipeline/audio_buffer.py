"""环形音频缓冲区 — 保留最近 N 秒音频"""
import numpy as np
from collections import deque


class AudioBuffer:
    """环形音频缓冲区"""
    
    def __init__(self, sample_rate: int = 16000, max_duration: float = 3.0):
        self.sample_rate = sample_rate
        self.max_frames = int(sample_rate * max_duration)
        self.buffer = deque(maxlen=self.max_frames)
    
    def write(self, frames: np.ndarray):
        """写入音频帧"""
        self.buffer.extend(frames)
    
    def read_all(self) -> np.ndarray:
        """读取全部缓冲区内容"""
        return np.array(list(self.buffer), dtype=np.float32)
    
    def read_last(self, duration: float = 0.5) -> np.ndarray:
        """读取最近 N 秒"""
        n_frames = int(self.sample_rate * duration)
        if len(self.buffer) < n_frames:
            return self.read_all()
        return np.array(list(self.buffer)[-n_frames:], dtype=np.float32)
    
    def clear(self):
        self.buffer.clear()
    
    @property
    def duration(self) -> float:
        return len(self.buffer) / self.sample_rate
