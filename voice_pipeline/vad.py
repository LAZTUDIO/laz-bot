"""VAD — 语音活动检测 (Silero VAD)"""
import numpy as np
from silero_vad import load_silero_vad, get_speech_timestamps


class VoiceActivityDetector:
    """基于 Silero VAD 的语音活动检测"""
    
    def __init__(self, sample_rate: int = 16000, threshold: float = 0.5):
        self.sample_rate = sample_rate
        self.threshold = threshold
        self._model = None
        self.speech_buffer = []  # 累积语音帧
        self.is_speaking = False
        self.silence_frames = 0
        self.silence_timeout_frames = 0  # 设置外部
    
    def load_model(self):
        """加载 VAD 模型"""
        if self._model is None:
            print("[VAD] Loading Silero VAD model...")
            self._model = load_silero_vad()
            print("[VAD] Model loaded")
    
    def process_frame(self, audio_chunk: np.ndarray) -> bool:
        """
        处理单帧音频
        返回: True = 检测到语音
        """
        if self._model is None:
            self.load_model()
        
        # SileroVAD expects int16
        audio_int16 = (audio_chunk * 32768).astype(np.int16)
        
        speech_prob = self._model(audio_int16, self.sample_rate)
        is_speech = speech_prob > self.threshold
        
        if is_speech:
            self.is_speaking = True
            self.speech_buffer.append(audio_chunk)
            self.silence_frames = 0
        else:
            if self.is_speaking:
                self.silence_frames += 1
                # Keep adding during grace period
                if self.silence_frames < self.silence_timeout_frames:
                    self.speech_buffer.append(audio_chunk)
                else:
                    self.is_speaking = False
        
        return is_speech
    
    def get_speech_segment(self) -> np.ndarray:
        """获取累积的语音段并清空缓冲区"""
        if not self.speech_buffer:
            return np.array([], dtype=np.float32)
        segment = np.concatenate(self.speech_buffer)
        self.speech_buffer = []
        return segment
    
    def has_speech(self) -> bool:
        return len(self.speech_buffer) > 0
    
    def reset(self):
        self.speech_buffer = []
        self.is_speaking = False
        self.silence_frames = 0
