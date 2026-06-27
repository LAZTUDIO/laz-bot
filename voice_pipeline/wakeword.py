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
        self.models: dict = {}  # name -> openwakeword Model
        self.thresholds: dict = {}  # name -> float
        self._on_wakeword: Optional[Callable] = None
        self._sample_rate = 16000

    def load_models(self, wake_word_names: list[str]):
        """加载 ONNX 唤醒词模型"""
        try:
            from openwakeword.model import Model
        except ImportError:
            logger.warning("openwakeword not installed, run: pip install openwakeword")
            return

        model_paths = []
        for name in wake_word_names:
            path = self.wake_words_dir / f"{name}.onnx"
            if path.exists():
                model_paths.append(str(path))
                self.thresholds[name] = 0.5
                logger.info(f"[WakeWord] Found model: {name} ({path.stat().st_size} bytes)")
            else:
                logger.warning(f"[WakeWord] Model not found: {path}")

        if not model_paths:
            logger.warning("[WakeWord] No ONNX models found")
            return

        try:
            # v0.4.0 API: single Model with multiple paths
            self._model = Model(wakeword_model_paths=model_paths)
            # Extract model names from the loaded model
            if hasattr(self._model, 'models'):
                for key in self._model.models.keys():
                    self.models[key] = key
                    logger.info(f"[WakeWord] Loaded: {key}")
            elif hasattr(self._model, 'class_mapping'):
                for key in self._model.class_mapping.keys():
                    self.models[key] = key
                    logger.info(f"[WakeWord] Loaded: {key}")
            else:
                # Fallback: use the names we provided
                for name in wake_word_names:
                    if Path(self.wake_words_dir / f"{name}.onnx").exists():
                        self.models[name] = name
                        logger.info(f"[WakeWord] Loaded (fallback mapping): {name}")

            logger.info(f"[WakeWord] Ready: {len(self.models)} model(s) loaded")
        except Exception as e:
            logger.error(f"[WakeWord] Failed to load: {e}")

    def set_callback(self, callback: Callable[[str], None]):
        """唤醒回调: callback(wake_word_name)"""
        self._on_wakeword = callback

    def process_frame(self, audio_chunk: np.ndarray) -> list[str]:
        """处理单帧音频 (1D, 16kHz, int16 or float32)"""
        if not hasattr(self, '_model'):
            return []

        result = self._model.predict(audio_chunk)
        # openWakeWord v0.4 returns dict like {'jiweisi': 0.92}
        if not isinstance(result, dict):
            return []

        matched = []
        for name, score in result.items():
            threshold = self.thresholds.get(name, 0.5)
            if score > threshold:
                matched.append(name)
                if self._on_wakeword:
                    self._on_wakeword(name)

        return matched

    def contains_wake_word(self, audio: np.ndarray) -> bool:
        """检测一段完整音频是否包含唤醒词（滑动窗口方式）"""
        if not hasattr(self, '_model'):
            return False

        # Ensure float32
        if audio.dtype == np.int16:
            audio = audio.astype(np.float32) / 32768.0

        # Run predict on the full clip — openWakeWord internally windows
        result = self._model.predict(audio)
        if not isinstance(result, dict):
            return False

        for name, score in result.items():
            if score > self.thresholds.get(name, 0.5):
                logger.info(f"[WakeWord] Detected '{name}' score={score:.3f}")
                if self._on_wakeword:
                    self._on_wakeword(name)
                return True

        return False

    def set_threshold(self, name: str, threshold: float):
        """设置特定唤醒词的阈值"""
        self.thresholds[name] = threshold
