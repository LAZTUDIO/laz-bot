"""音频采集 — PyAudio + ALSA"""
import time
import numpy as np
import pyaudio
import threading
from typing import Callable, Optional


class AudioCapture:
    """
    音频采集模块
    自动检测音频设备, 支持 USB / 蓝牙 / HDMI 音频
    """
    
    def __init__(self, 
                 sample_rate: int = 16000,
                 chunk_size: int = 512,
                 input_device: str = "",
                 output_device: str = ""):
        self.sample_rate = sample_rate
        self.chunk_size = chunk_size
        self.input_device_name = input_device
        self.output_device_name = output_device
        self.running = False
        self._stream = None
        self._pyaudio_instance = None
        self._on_audio_callback: Optional[Callable] = None
    
    def list_devices(self) -> list:
        """列出所有音频设备"""
        p = pyaudio.PyAudio()
        devices = []
        for i in range(p.get_device_count()):
            info = p.get_device_info_by_index(i)
            devices.append({
                "index": i,
                "name": info["name"],
                "channels_in": info["maxInputChannels"],
                "channels_out": info["maxOutputChannels"],
                "sample_rate": info["defaultSampleRate"],
            })
        p.terminate()
        return devices
    
    def _find_device(self, devices: list, name_keyword: str, direction: str = "input") -> int:
        """根据名称关键词查找设备索引"""
        ch_key = "channels_in" if direction == "input" else "channels_out"
        for dev in devices:
            if name_keyword.lower() in dev["name"].lower() and dev[ch_key] > 0:
                return dev["index"]
        return None
    
    def set_callback(self, callback: Callable[[np.ndarray], None]):
        """设置音频数据回调"""
        self._on_audio_callback = callback
    
    def start(self) -> bool:
        """启动音频采集"""
        if self.running:
            return True
        
        self._pyaudio_instance = pyaudio.PyAudio()
        devices = self.list_devices()
        
        # Find input device
        input_idx = None
        if self.input_device_name:
            input_idx = self._find_device(devices, self.input_device_name, "input")
        
        if input_idx is None:
            # Try to find any input device
            for dev in devices:
                if dev["channels_in"] > 0 and "loopback" not in dev["name"].lower():
                    input_idx = dev["index"]
                    break
        
        if input_idx is None:
            print("[Audio] No input device found, using default")
        
        try:
            self._stream = self._pyaudio_instance.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=self.sample_rate,
                input=True,
                input_device_index=input_idx,
                frames_per_buffer=self.chunk_size,
                stream_callback=self._audio_callback,
            )
            self.running = True
            print(f"[Audio] Capture started (device index={input_idx})")
            return True
        except Exception as e:
            print(f"[Audio] Failed to start capture: {e}")
            return False
    
    def _audio_callback(self, in_data, frame_count, time_info, status):
        """PyAudio 回调 — 将音频数据传给注册的处理器"""
        if self._on_audio_callback:
            audio_array = np.frombuffer(in_data, dtype=np.int16).astype(np.float32) / 32768.0
            self._on_audio_callback(audio_array)
        return (None, pyaudio.paContinue)
    
    def play_audio(self, audio_data: np.ndarray):
        """播放音频（TTS 输出用）"""
        if self._pyaudio_instance is None:
            return
        try:
            stream = self._pyaudio_instance.open(
                format=pyaudio.paFloat32,
                channels=1,
                rate=self.sample_rate,
                output=True,
            )
            stream.write(audio_data.tobytes())
            stream.stop_stream()
            stream.close()
        except Exception as e:
            print(f"[Audio] Playback error: {e}")
    
    def stop(self):
        self.running = False
        if self._stream:
            self._stream.stop_stream()
            self._stream.close()
        if self._pyaudio_instance:
            self._pyaudio_instance.terminate()
