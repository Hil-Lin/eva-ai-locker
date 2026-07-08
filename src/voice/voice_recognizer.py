# src/voice/voice_recognizer.py
"""
离线语音识别器 — 基于 Vosk + sounddevice

默认麦克风: PCM2902 USB (card 3, 48kHz→16kHz plughw重采样)
默认Vosk模型: models/vosk-model-cn-0.22 (大模型, 2GB)

用法:
    rec = VoiceRecognizer(model_path="...", audio_device="PCM2902")
    rec.start_listening(lambda text: print(f"识别: {text}"))
    ...
    rec.stop_listening()
"""

import queue
import threading
import json
import numpy as np
import sounddevice as sd
from vosk import Model, KaldiRecognizer


class VoiceRecognizer:
    """离线语音识别器（Vosk + sounddevice）"""

    def __init__(self, model_path: str = "models/vosk-model-cn-0.22",
                 sample_rate: int = 16000, audio_device: str = "PCM2902"):
        """
        Args:
            model_path: Vosk 模型路径
            sample_rate: 采样率 (8000/16000/44100)
            audio_device: 录音设备名 ("default", "plughw:1,0" 等)
        """
        self.model = Model(model_path)
        self.recognizer = KaldiRecognizer(self.model, sample_rate)
        self.sample_rate = sample_rate
        self.audio_device = audio_device
        self.audio_queue = queue.Queue(maxsize=100)
        self.is_listening = False
        self._stream = None
        self._callbacks: list = []

    # ── 公共接口 ──

    def start_listening(self, callback=None):
        """
        开始监听语音输入。

        Args:
            callback: 收到完整句子时的回调 callback(text: str)
        """
        if callback:
            self._callbacks.append(callback)

        if self.is_listening:
            return

        self.is_listening = True

        # 音频采集线程
        self._capture_thread = threading.Thread(
            target=self._audio_capture_thread, daemon=True)
        self._capture_thread.start()

        # 识别处理线程
        self._process_thread = threading.Thread(
            target=self._process_audio_thread, daemon=True)
        self._process_thread.start()

    def add_callback(self, callback):
        """添加额外的识别回调"""
        self._callbacks.append(callback)

    def stop_listening(self):
        """停止监听"""
        self.is_listening = False
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None

    # ── 内部实现 ──

    def _audio_capture_thread(self):
        """音频采集 — 用 sounddevice InputStream 回调模式"""
        try:
            # 将设备名转为索引
            device = None
            if self.audio_device and self.audio_device != "default":
                try:
                    device = int(self.audio_device)
                except ValueError:
                    # 按名称查找设备
                    devices = sd.query_devices()
                    device_lower = self.audio_device.lower()
                    for i, dev in enumerate(devices):
                        if device_lower in dev.get('name', '').lower():
                            device = i
                            break
                    if device is None:
                        print(f"[VoiceRec] 未找到设备 {self.audio_device}，使用默认")
                        device = None

            def audio_callback(indata, frames, time_info, status):
                """sounddevice 回调 — 将音频数据放入队列"""
                if status:
                    print(f"[VoiceRec] 音频状态: {status}")
                # 立体声→单声道平均（避免盲取左声道的问题）
                if indata.shape[1] >= 2:
                    mono = indata.mean(axis=1)
                else:
                    mono = indata[:, 0]
                # 增益归一化：安静信号自动放大
                rms = np.sqrt(np.mean(mono ** 2))
                if 1e-6 < rms < 0.02:
                    mono = mono * (0.08 / rms)
                data = (mono * 32767).clip(-32768, 32767).astype(np.int16).tobytes()
                try:
                    self.audio_queue.put_nowait(data)
                except queue.Full:
                    pass  # 丢弃旧数据，防止积压

            self._stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=1,
                device=device,
                dtype='float32',
                blocksize=4000,
                callback=audio_callback,
            )
            self._stream.start()

            # 等待停止信号
            while self.is_listening:
                sd.sleep(100)

        except Exception as e:
            if self.is_listening:
                print(f"[VoiceRec] 音频采集错误: {e}")
        finally:
            if self._stream is not None:
                try:
                    self._stream.stop()
                    self._stream.close()
                except Exception:
                    pass

    def _process_audio_thread(self):
        """音频处理 — 喂给 Vosk 识别"""
        while self.is_listening:
            try:
                data = self.audio_queue.get(timeout=0.2)
                if self.recognizer.AcceptWaveform(data):
                    result = json.loads(self.recognizer.Result())
                    text = result.get("text", "").strip()
                    if text:
                        for cb in self._callbacks:
                            try:
                                cb(text)
                            except Exception as e:
                                print(f"[VoiceRec] 回调异常: {e}")
            except queue.Empty:
                continue
            except Exception as e:
                if self.is_listening:
                    print(f"[VoiceRec] 处理错误: {e}")

    # ── 工具方法 ──

    def recognize_file(self, audio_file: str) -> str:
        """从 WAV 文件识别文本"""
        import wave
        try:
            with wave.open(audio_file, "rb") as wf:
                if wf.getsampwidth() != 2:
                    raise ValueError("只支持 16-bit WAV")
                data = wf.readframes(wf.getnframes())

            rec = KaldiRecognizer(self.model, wf.getframerate() if 'wf' in dir() else self.sample_rate)
            if rec.AcceptWaveform(data):
                return json.loads(rec.Result()).get("text", "")
            return ""
        except Exception as e:
            print(f"[VoiceRec] 文件识别错误: {e}")
            return ""

    def get_partial(self) -> str:
        """获取部分识别结果（中间结果）"""
        return json.loads(self.recognizer.PartialResult()).get("partial", "")

    @staticmethod
    def list_microphones() -> list:
        """列出可用录音设备"""
        mics = []
        devices = sd.query_devices()
        for i, dev in enumerate(devices):
            if dev.get('max_input_channels', 0) > 0:
                mics.append({
                    "index": i,
                    "name": dev.get('name', '?'),
                    "channels": dev.get('max_input_channels', 0),
                    "sample_rate": dev.get('default_samplerate', 0),
                })
        return mics


# ── 独立测试 ──
if __name__ == "__main__":
    import sys
    import time

    # 列出设备
    print("可用麦克风:")
    for m in VoiceRecognizer.list_microphones():
        print(f"  [{m['index']}] {m['name']} ({m['channels']}ch)")

    device = sys.argv[1] if len(sys.argv) > 1 else "default"
    print(f"\n使用设备: {device}")
    print("开始识别，请说话... (Ctrl+C 退出)\n")

    def on_text(text):
        print(f">>> {text}")

    rec = VoiceRecognizer(audio_device=device)
    rec.start_listening(on_text)

    try:
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\n停止...")
    finally:
        rec.stop_listening()
