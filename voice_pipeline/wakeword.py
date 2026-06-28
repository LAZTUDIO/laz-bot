"""唤醒词检测 — openWakeWord v0.4.0"""
import numpy as np
from pathlib import Path
from typing import Callable, Optional
import logging

logger = logging.getLogger("lazbot.wakeword")


class WakeWordDetector:
    """基于 openWakeWord v0.4.0 的唤醒词检测"""

    def __init__(self, wake_words_dir: str = "wake_words"):
        self.wake_words_dir = Path(wake_words_dir)
        self._model = None
        self.model_names: list[str] = []
        self.thresholds: dict[str, float] = {}
        self._on_wakeword: Optional[Callable] = None
        self._sample_rate = 16000
        self._frame_size = 1280  # openWakeWord 固定帧大小 (80ms @16kHz)

    def load_models(self, wake_word_names: list[str]):
        """加载 ONNX 唤醒词模型"""
        try:
            from openwakeword.model import Model
        except ImportError:
            logger.warning("openwakeword not installed")
            return

        model_paths = []
        for name in wake_word_names:
            path = self.wake_words_dir / f"{name}.onnx"
            if path.exists():
                model_paths.append(str(path))
                self.thresholds[name] = 0.5
                self.model_names.append(name)
                logger.info(f"[WakeWord] Found model: {name} ({path.stat().st_size} bytes)")
            else:
                logger.warning(f"[WakeWord] Model not found: {path}")

        if not model_paths:
            logger.warning("[WakeWord] No ONNX models found")
            return

        try:
            self._model = Model(wakeword_model_paths=model_paths)
            logger.info(f"[WakeWord] Ready: {len(model_paths)} model(s) loaded")
        except Exception as e:
            logger.error(f"[WakeWord] Failed to load: {e}")

    def set_callback(self, callback: Callable[[str], None]):
        self._on_wakeword = callback

    def _audio_to_16k_float32(self, audio: np.ndarray, source_sample_rate: int) -> np.ndarray:
        """统一转成 16kHz float32"""
        # int16 → float32
        if audio.dtype == np.int16:
            audio = audio.astype(np.float32) / 32768.0
        elif audio.dtype != np.float32:
            audio = audio.astype(np.float32)

        # 降采样到 16kHz
        if source_sample_rate != 16000:
            target_len = int(len(audio) * 16000 / source_sample_rate)
            if target_len > 0:
                audio = np.interp(
                    np.linspace(0, len(audio) - 1, target_len),
                    np.arange(len(audio)),
                    audio
                ).astype(np.float32)
        return audio

    def process_frame(self, audio_chunk: np.ndarray, source_sample_rate: int = 16000) -> list[str]:
        """处理单帧音频 (1280 samples @16kHz 或等时长)"""
        if self._model is None:
            return []

        # 统一格式
        audio = self._audio_to_16k_float32(audio_chunk, source_sample_rate)

        # 如果长度不是 _frame_size，裁剪或补齐
        if len(audio) != self._frame_size:
            if len(audio) > self._frame_size:
                audio = audio[:self._frame_size]
            else:
                audio = np.pad(audio, (0, self._frame_size - len(audio)))

        result = self._model.predict(audio)
        if not isinstance(result, dict):
            return []

        matched = []
        for name in self.model_names:
            score = result.get(name, 0.0)
            threshold = self.thresholds.get(name, 0.5)
            if score > threshold:
                matched.append(name)
                if self._on_wakeword:
                    self._on_wakeword(name)

        return matched

    def contains_wake_word(self, audio: np.ndarray, source_sample_rate: int = 48000) -> bool:
        """逐帧扫描整段音频检测唤醒词

        将音频切成 openWakeWord 标准的 1280-sample 帧，
        每帧独立预测，任一帧触发即返回 True。
        """
        if self._model is None:
            return False

        # 统一转 16kHz float32
        audio = self._audio_to_16k_float32(audio, source_sample_rate)

        # 切帧
        step = self._frame_size // 2  # 50% 重叠
        max_score = 0.0
        best_name = ""

        for start in range(0, len(audio) - self._frame_size + 1, step):
            frame = audio[start:start + self._frame_size]
            if len(frame) < self._frame_size:
                continue
            result = self._model.predict(frame)
            if not isinstance(result, dict):
                continue
            for name in self.model_names:
                score = result.get(name, 0.0)
                if score > max_score:
                    max_score = score
                    best_name = name
                threshold = self.thresholds.get(name, 0.5)
                if score > threshold:
                    logger.info(f"[WakeWord] Detected '{name}' score={score:.3f} at frame {start//step}")
                    if self._on_wakeword:
                        self._on_wakeword(name)
                    return True

        if max_score > 0:
            logger.debug(f"[WakeWord] Max score: {best_name}={max_score:.3f} (threshold={self.thresholds.get(best_name, 0.5)})")
        return False

    def set_threshold(self, name: str, threshold: float):
        self.thresholds[name] = threshold
