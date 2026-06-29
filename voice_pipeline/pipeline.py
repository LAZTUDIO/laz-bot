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

    def __init__(self, config: dict, model_router, llm_router, memory_service, cognitive_cycle=None):
        self.config = config
        self.model_router = model_router
        self.llm = llm_router
        self.memory = memory_service
        self.cycle = cognitive_cycle  # 认知循环实例（与聊天调试同源）

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
        logger.info(f"[Voice] Wake-word-first mode (speech>{self.speech_threshold:.4f}, silence<{self.silence_threshold:.4f}, timeout={self.silence_timeout}s)")

        try:
            while self.running:
                # ═══ 持续监听唤醒词（流式，不经过VAD）═══
                if self._wakeword:
                    await self.send_event(ws, "status", "listening")
                    wake_hit = await self._listen_for_wake_word(cap, ws)
                    if not wake_hit:
                        continue
                    await self.send_event(ws, "status", "wake_word_detected")

                # ═══ 唤醒后 → VAD 捕获语音 → STT → LLM → TTS ═══
                audio_data = await self._capture_speech(cap, ws)
                if audio_data is None or len(audio_data) < self.frame_size * 3:
                    await self.send_event(ws, "status", "listening")
                    continue

                duration = len(audio_data) / self.sample_rate
                logger.info(f"[Voice] Captured {duration:.1f}s audio")
                await self.send_event(ws, "status", "transcribing")
                text = await self._transcribe(audio_data)
                if not text or len(text.strip()) < 2:
                    await self.send_event(ws, "status", "listening")
                    continue

                logger.info(f"[Voice] Heard: {text}")
                await self.send_event(ws, "transcript", text)

                # ── LLM ──
                await self.send_event(ws, "status", "thinking")
                if self.cycle:
                    reply_text = await self.cycle.process_text(text, session_id)
                    content = str(reply_text) if reply_text else "(空)"
                else:
                    reply = await self.llm.chat_completion(
                        messages=[{"role": "user", "content": text}],
                    )
                    if "error" in reply:
                        await self.send_event(ws, "error", reply["error"])
                        continue
                    content = reply["choices"][0]["message"]["content"]

                logger.info(f"[Voice] Reply: {content[:60]}...")
                await self.send_event(ws, "response", content)

                # ── TTS ──
                await self.send_event(ws, "status", "speaking")
                audio_out = await self._synthesize(content)
                if audio_out is not None:
                    audio_out = audio_out * self.output_gain
                    out_rms = float(np.sqrt(np.mean(audio_out ** 2)))
                    await self.send_event(ws, "vu_output", {
                        "rms": round(out_rms, 4),
                        "db": round(20 * np.log10(max(out_rms, 1e-6)), 1),
                    })
                    play.write(audio_out)

                # ── 记忆 ──
                if not self.cycle and self.memory:
                    asyncio.create_task(self.memory.store_interaction(session_id, "user", text))
                    asyncio.create_task(self.memory.store_interaction(session_id, "assistant", content))

                # 对话后的短暂冷却
                await asyncio.sleep(0.5)

        except Exception as e:
            logger.error(f"[Voice] Pipeline error: {e}")
            await self.send_event(ws, "error", str(e))
        finally:
            cap.stop()
            play.stop()
            await self.send_event(ws, "status", "pipeline_stopped")

    async def _listen_for_wake_word(self, cap, ws) -> bool:
        """持续监听唤醒词 - 累积多帧后喂给模型"""
        import time
        t0 = time.time()
        vu_last = 0
        buffer = []

        # 模型需要 1280 samples@16kHz = 3840 samples@48kHz
        # ALSA frame=1024 -> 需要 4 帧
        frames_per_window = max(1, int(1280 * self.sample_rate / 16000 / self.frame_size))
        # 修正：向上取整，确保至少 3840 samples@48kHz → 1280 samples@16kHz
        if frames_per_window * self.frame_size < 3840:
            frames_per_window += 1

        # 初始状态通知
        await self.send_event(ws, "status", "listening_for_wake_word")
        ww_names = self._wakeword.model_names if self._wakeword else []
        ww_thresh = self._wakeword.thresholds.get(ww_names[0], 0.3) if ww_names else 0.3 if self._wakeword else 0
        await self.send_event(ws, "wake_score", {
            "name": ww_names[0] if ww_names else "unknown",
            "score": 0,
            "threshold": round(ww_thresh, 2),
            "hit": False,
        })

        while self.running:
            arr = cap.read() * self.input_gain
            buffer.append(arr)

            # VU 更新
            now = time.time()
            if now - vu_last > 0.20:
                rms = float((arr ** 2).mean() ** 0.5)
                await self.send_event(ws, "vu_input", {
                    "rms": round(rms, 5),
                    "db": round(20 * __import__('numpy').log10(max(rms, 1e-6)), 1),
                })
                vu_last = now

            # 积累够了 -> 喂给唤醒词模型
            if len(buffer) >= frames_per_window:
                import numpy as np
                chunk = np.concatenate(buffer[-frames_per_window:])
                buffer = buffer[-2:]

                if self._wakeword and self._wakeword._model:
                    target_len = 1280
                    src_len = len(chunk)
                    if src_len != target_len:
                        indices = np.linspace(0, src_len - 1, target_len)
                        audio_16k = np.interp(indices, np.arange(src_len), chunk).astype(np.float32)
                    else:
                        audio_16k = chunk.astype(np.float32)

                    result = self._wakeword._model.predict(audio_16k)
                    if isinstance(result, dict):
                        for name in self._wakeword.model_names:
                            score = result.get(name, 0.0)
                            threshold = self._wakeword.thresholds.get(name, 0.3)
                            # 推送每一帧的唤醒词得分（所有分数都推，方便调试）
                            await self.send_event(ws, "wake_score", {
                                "name": name,
                                "score": round(score, 4),
                                "threshold": round(threshold, 2),
                                "hit": score > threshold,
                            })
                            if score > threshold:
                                logger.info(f"[WakeWord] Detected '{name}' score={score:.3f}")
                                await self.send_event(ws, "wake_hit", {"name": name, "score": round(score, 4)})
                                return True

            # ONNX 状态定期重置
            if time.time() - t0 > 60:
                if self._wakeword and hasattr(self._wakeword._model, 'reset'):
                    try:
                        self._wakeword._model.reset()
                    except Exception:
                        pass
                t0 = time.time()

            await asyncio.sleep(0.005)

        return False

    async def _capture_speech(self, cap, ws) -> np.ndarray | None:
        """唤醒后 → VAD 捕获完整语音段"""
        chunks = []
        pre_buffer = deque(maxlen=int(0.3 * self.sample_rate / self.frame_size))
        total_frames = 0
        max_frames = int(self.max_recording_sec * self.sample_rate / self.frame_size)
        idle_limit = int(self.silence_timeout * self.sample_rate / self.frame_size)
        idle = 0
        voice_on = False

        await self.send_event(ws, "status", "listening_for_speech")

        while self.running and total_frames < max_frames:
            arr = cap.read() * self.input_gain
            total_frames += 1
            energy = float(np.sqrt(np.mean(arr ** 2)))

            if not voice_on:
                pre_buffer.append(arr)
                if energy > self.speech_threshold:
                    voice_on = True
                    chunks.extend(pre_buffer)
                    chunks.append(arr)
                    await self.send_event(ws, "status", "recording")
            else:
                chunks.append(arr)
                if energy < self.silence_threshold:
                    idle += 1
                    if idle > idle_limit:
                        break
                else:
                    idle = 0

            await asyncio.sleep(0)

        return np.concatenate(chunks) if voice_on and len(chunks) >= 3 else None

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
