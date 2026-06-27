"""语音管道 — 串联 采集→智能VAD→STT→LLM→TTS→播放
使用 ALSA arecord/aplay 子进程，绕过 PortAudio/PulseAudio。

VAD 策略:
  - 启动时自动校准环境噪音基线
  - 双阈值: 高阈值触发 (开始说话), 低阈值静默 (停止)
  - 预录音缓冲 (防丢首音节)
  - 最大录音长度硬截断
  - 短静默超时 (模拟自然对话停顿)
"""
import asyncio
import json
import logging
import time
from collections import deque

import numpy as np

from .alsa_capture import AlsaCapture, AlsaPlayback

logger = logging.getLogger("laz-bot.voice")


class VoicePipeline:
    """语音全双工管道，通过 WebSocket 推送状态"""

    def __init__(self, config: dict, model_router, llm_router, memory_service):
        self.config = config
        self.model_router = model_router
        self.llm = llm_router
        self.memory = memory_service

        vc = config.get("voice", {})
        self.sample_rate = vc.get("sample_rate", 48000)
        self.frame_size = vc.get("frame_size", 1024)
        self.vad_threshold = vc.get("vad_threshold", 0.5)
        self.silence_timeout = vc.get("silence_timeout", 1.5)
        self.wake_threshold = vc.get("wake_threshold", 0.7)
        self.wake_words = vc.get("wake_words", [])
        self.input_device = vc.get("input_device", "") or "plughw:2,0"
        self.output_device = vc.get("output_device", "") or "plughw:2,0"

        # 高级 VAD 参数
        self.speech_threshold = vc.get("speech_threshold", 0.02)
        self.silence_threshold = vc.get("silence_threshold", 0.008)
        self.silence_timeout = vc.get("silence_timeout", 0.6)
        self.max_recording_sec = vc.get("max_recording_sec", 15.0)
        self.pre_speech_sec = vc.get("pre_speech_sec", 0.4)
        self.noise_adapt = vc.get("noise_adapt", True)
        self.noise_baseline = 0.001

        # 音量 / VU 表
        self.input_gain = float(vc.get("input_gain", 1.0))
        self.output_gain = float(vc.get("output_gain", 1.0))
        self.vu_interval = vc.get("vu_interval", 0.08)  # VU 推送间隔 (秒)
        self._last_vu_push = 0.0
        self.in_conversation = False

        self.running = False
        self._wakeword = None

        # 唤醒词
        wake_model_path = vc.get("wake_model_path", "")
        wake_word_names = vc.get("wake_words", [])
        if wake_model_path and wake_word_names:
            from .wakeword import WakeWordDetector
            # 复制 ONNX 到标准目录（如果路径不在 wake_words 下）
            self._wakeword = WakeWordDetector(wake_words_dir="wake_words")
            self._wakeword.load_models(wake_word_names)
            wake_threshold = vc.get("wake_threshold", 0.5)
            for name in wake_word_names:
                self._wakeword.set_threshold(name, wake_threshold)

    async def send_event(self, ws, event_type: str, data=None):
        try:
            await ws.send_text(json.dumps({"type": event_type, "data": data}))
        except Exception:
            pass

    async def _calibrate_noise(self, cap, duration_sec: float = 0.8) -> float:
        """自动校准环境噪音：采集 N 秒取 RMS 中位数"""
        frames = int(self.sample_rate / self.frame_size * duration_sec)
        energies = []
        for _ in range(frames):
            arr = cap.read()
            energies.append(np.sqrt(np.mean(arr ** 2)))
            await asyncio.sleep(0)
        baseline = float(np.median(energies)) if energies else 0.001
        logger.info(f"[Voice] Noise baseline calibrated: {baseline:.6f}")
        return baseline

    async def run(self, ws, session_id: str = None):
        if not session_id:
            import uuid
            session_id = str(uuid.uuid4())

        self.running = True
        await self.send_event(ws, "status", "pipeline_started")

        cap = AlsaCapture(
            device=self.input_device, sample_rate=self.sample_rate,
            channels=1, frame_size=self.frame_size,
        )
        cap.start()
        play = AlsaPlayback(
            device=self.output_device, sample_rate=self.sample_rate, channels=1,
        )
        play.start()

        # 校准噪音基线
        if self.noise_adapt:
            await self.send_event(ws, "status", "calibrating")
            self.noise_baseline = await self._calibrate_noise(cap)
            # 基于基线动态调整阈值（如果用户没手动设）
            if self.speech_threshold == 0.02:   # 默认值 → 自动
                self.speech_threshold = max(self.noise_baseline * 4.0, 0.008)
            if self.silence_threshold == 0.008:  # 默认值 → 自动
                self.silence_threshold = max(self.noise_baseline * 2.0, 0.004)

        await self.send_event(ws, "status", "listening")
        logger.info(f"[Voice] Listening (speech>{self.speech_threshold:.4f}, silence<{self.silence_threshold:.4f}, timeout={self.silence_timeout}s, max={self.max_recording_sec}s)")

        try:
            while self.running:
                await self.send_event(ws, "status", "waiting_speech")

                # ── 预录音环形缓冲 ──
                pre_buffer_size = int(self.sample_rate / self.frame_size * self.pre_speech_sec)
                pre_buffer = deque(maxlen=pre_buffer_size)

                chunks = []
                voice_detected = False
                silence_frames = 0
                total_frames = 0
                max_frames = int(self.sample_rate / self.frame_size * self.max_recording_sec)
                silence_limit = int(self.silence_timeout * self.sample_rate / self.frame_size)
                idle_timeout = int(self.sample_rate / self.frame_size * 5)  # 5s 无语音则退出等待

                idle = 0
                vu_frames = 0
                vu_acc_energy = 0.0
                vu_push_every = max(1, int(self.vu_interval * self.sample_rate / self.frame_size))

                while self.running and total_frames < max_frames:
                    arr = cap.read() * self.input_gain  # 软件增益
                    energy = np.sqrt(np.mean(arr ** 2))
                    pre_buffer.append(arr)
                    total_frames += 1

                    # ── VU 表：每 N 帧推送一次 RMS ──
                    vu_acc_energy += energy
                    vu_frames += 1
                    if vu_frames >= vu_push_every:
                        avg_rms = vu_acc_energy / vu_frames
                        await self.send_event(ws, "vu_input", {
                            "rms": round(float(avg_rms), 5),
                            "db": round(20 * np.log10(max(avg_rms, 1e-6)), 1),
                            "peak": round(float(np.max(np.abs(arr))), 4),
                        })
                        vu_acc_energy = 0.0
                        vu_frames = 0

                    if voice_detected:
                        # 正在录音 → 用低阈值判断静默
                        chunks.append(arr)
                        if energy < self.silence_threshold:
                            silence_frames += 1
                            if silence_frames > silence_limit:
                                break  # 足够长的静默 → 断句
                        else:
                            silence_frames = 0  # 又有声音 → 重置
                    else:
                        # 等待语音 → 用高阈值触发
                        if energy > self.speech_threshold:
                            voice_detected = True
                            # 把预录音缓冲也加进去
                            chunks.extend(pre_buffer)
                            chunks.append(arr)
                            self.in_conversation = True
                            await self.send_event(ws, "status", "recording")
                        else:
                            idle += 1
                            if idle > idle_timeout:
                                break  # 超时 → 回到外层循环

                    await asyncio.sleep(0)

                # 达到最大录音长度 → 强制截断
                if total_frames >= max_frames and voice_detected:
                    logger.info(f"[Voice] Max recording reached ({self.max_recording_sec}s), cutting")

                if not voice_detected or len(chunks) < 3:
                    # 没检测到有效语音
                    continue

                # ── 唤醒词检测 ──
                audio_data = np.concatenate(chunks)
                if self._wakeword:
                    if not self._wakeword.contains_wake_word(audio_data):
                        logger.info("[Voice] Wake word not detected — ignored")
                        await self.send_event(ws, "status", "listening")
                        continue

                # ── STT ──
                duration = len(audio_data) / self.sample_rate
                logger.info(f"[Voice] Captured {duration:.1f}s audio")
                await self.send_event(ws, "status", "transcribing")
                text = await self._transcribe(audio_data)

                if not text or len(text.strip()) < 2:
                    await self.send_event(ws, "status", "hearing_noise")
                    self.in_conversation = False
                    continue

                logger.info(f"[Voice] Heard: {text}")
                await self.send_event(ws, "transcript", text)

                # ── LLM ──
                await self.send_event(ws, "status", "thinking")
                reply = await self.llm.chat_completion(
                    messages=[{"role": "user", "content": text}],
                )

                if "error" in reply:
                    await self.send_event(ws, "error", reply["error"])
                    self.in_conversation = False
                    continue

                content = reply["choices"][0]["message"]["content"]
                logger.info(f"[Voice] Reply: {content[:60]}...")
                await self.send_event(ws, "response", content)

                # ── TTS ──
                await self.send_event(ws, "status", "speaking")
                audio_out = await self._synthesize(content)
                if audio_out is not None:
                    audio_out = audio_out * self.output_gain  # 软件增益
                    out_rms = float(np.sqrt(np.mean(audio_out ** 2)))
                    await self.send_event(ws, "vu_output", {
                        "rms": round(out_rms, 4),
                        "db": round(20 * np.log10(max(out_rms, 1e-6)), 1),
                    })
                    play.write(audio_out)

                # ── 记忆 ──
                if self.memory:
                    asyncio.create_task(
                        self.memory.store_interaction(session_id, "user", text))
                    asyncio.create_task(
                        self.memory.store_interaction(session_id, "assistant", content))

                await self.send_event(ws, "status", "listening")
                # 对话后的短暂冷却，避免立即重新触发
                self.in_conversation = False

        except Exception as e:
            logger.error(f"[Voice] Pipeline error: {e}")
            await self.send_event(ws, "error", str(e))
        finally:
            cap.stop()
            play.stop()
            await self.send_event(ws, "status", "pipeline_stopped")

    async def _transcribe(self, audio: np.ndarray) -> str:
        entry = self.model_router.get_active_entry("stt")
        if not entry:
            return ""

        from .stt_client import STTClient
        client = STTClient(
            api_key=entry.get("api_key", ""),
            base_url=entry.get("base_url", "https://api.siliconflow.cn/v1"),
            model=entry.get("model_id", "FunAudioLLM/SenseVoiceSmall"),
        )
        try:
            return await client.transcribe(audio, self.sample_rate)
        finally:
            await client.close()

    async def _synthesize(self, text: str) -> np.ndarray | None:
        entry = self.model_router.get_active_entry("tts")
        if not entry:
            return None

        model_id = entry.get("model_id", "fnlp/MOSS-TTSD-v0.5")
        voice = entry.get("voice", f"{model_id}:alex")
        speed = float(entry.get("speed", 1.0))
        fmt = entry.get("response_format", "mp3")

        from .tts_client import TTSClient
        client = TTSClient(
            api_key=entry.get("api_key", ""),
            base_url=entry.get("base_url", "https://api.siliconflow.cn/v1"),
            model=model_id,
            voice=voice,
            speed=speed,
            response_format=fmt,
        )
        try:
            return await client.synthesize(text)
        finally:
            await client.close()

    def stop(self):
        self.running = False
        self._wakeword = None

        # 唤醒词
        wake_model_path = vc.get("wake_model_path", "")
        wake_word_names = vc.get("wake_words", [])
        if wake_model_path and wake_word_names:
            from .wakeword import WakeWordDetector
            # 复制 ONNX 到标准目录（如果路径不在 wake_words 下）
            self._wakeword = WakeWordDetector(wake_words_dir="wake_words")
            self._wakeword.load_models(wake_word_names)
            wake_threshold = vc.get("wake_threshold", 0.5)
            for name in wake_word_names:
                self._wakeword.set_threshold(name, wake_threshold)
