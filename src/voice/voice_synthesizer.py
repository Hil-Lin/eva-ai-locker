# src/voice/voice_synthesizer.py

import subprocess
import tempfile
import os
import threading
import queue

class VoiceSynthesizer:
    """语音合成器（基于eSpeak + aplay）"""

    def __init__(self, language="zh", speed=150, pitch=50,
                 audio_device="default"):
        """
        初始化语音合成器

        Args:
            language: 语言代码 (zh:中文, en:英文)
            speed: 语速 (80-260)
            pitch: 音调 (0-99)
            audio_device: ALSA 播放设备 ("default", "hw:0,0", "plughw:0,0")
        """
        self.language = language
        self.speed = speed
        self.pitch = pitch
        self.audio_device = audio_device
        self.audio_queue = queue.Queue()
        self.is_playing = False
        self._espeak_available = None  # 延迟检测

    def speak(self, text, blocking=False):
        """
        合成并播放语音

        Args:
            text: 要合成的文本
            blocking: 是否阻塞直到播放完成

        Returns:
            bool: 是否成功
        """
        try:
            # 创建临时WAV文件
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp_file:
                wav_file = tmp_file.name

            # 使用eSpeak生成语音
            cmd = [
                'espeak',
                '-v', self.language,
                '-s', str(self.speed),
                '-p', str(self.pitch),
                '-w', wav_file,
                text
            ]

            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                print(f"eSpeak错误: {result.stderr}")
                os.unlink(wav_file)
                return False

            # 播放语音
            if blocking:
                self._play_audio(wav_file)
            else:
                threading.Thread(target=self._play_audio, args=(wav_file,)).start()

            return True

        except Exception as e:
            print(f"语音合成错误: {e}")
            return False

    def _play_audio(self, wav_file):
        """播放WAV文件"""
        try:
            # 使用 aplay 播放音频，可指定设备
            if self.audio_device and self.audio_device != "default":
                cmd = ['aplay', '-D', self.audio_device, wav_file]
            else:
                cmd = ['aplay', wav_file]
            subprocess.run(cmd, capture_output=True)
        finally:
            # 删除临时文件
            if os.path.exists(wav_file):
                os.unlink(wav_file)

    def speak_async(self, text):
        """
        异步合成语音（放入队列）

        Args:
            text: 要合成的文本
        """
        self.audio_queue.put(text)
        if not self.is_playing:
            self._start_playback_thread()

    def _start_playback_thread(self):
        """启动播放线程"""
        self.is_playing = True
        threading.Thread(target=self._playback_thread).start()

    def _playback_thread(self):
        """播放线程"""
        while not self.audio_queue.empty():
            text = self.audio_queue.get()
            self.speak(text, blocking=True)
            self.audio_queue.task_done()
        self.is_playing = False

    def test_tone(self, frequency: int = 440, duration: float = 0.5) -> bool:
        """
        播放测试音（用 speaker-test 或 sox）。

        Args:
            frequency: 频率(Hz)，440=A4
            duration: 时长(秒)

        Returns:
            是否成功
        """
        try:
            # 方案1: speaker-test
            cmd = ['speaker-test', '-t', 'sine', '-f', str(frequency),
                   '-l', '1', '-D', self.audio_device]
            result = subprocess.run(cmd, capture_output=True, timeout=5)
            if result.returncode == 0:
                return True
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

        # 方案2: 用 sox 生成短音调
        try:
            cmd = ['sox', '-n', '-t', 'wav', '-', 'synth', str(duration),
                   'sine', str(frequency)]
            sox_proc = subprocess.Popen(cmd, stdout=subprocess.PIPE)
            if self.audio_device != "default":
                play_cmd = ['aplay', '-D', self.audio_device]
            else:
                play_cmd = ['aplay']
            play_proc = subprocess.Popen(play_cmd, stdin=sox_proc.stdout)
            sox_proc.stdout.close()
            play_proc.wait(timeout=5)
            return play_proc.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

        # 方案3: 直接用 Python 生成 WAV 并播放
        try:
            import struct
            import math
            sample_rate = 44100
            num_samples = int(sample_rate * duration)
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
                wav_path = f.name
                # 写 WAV 头
                data_size = num_samples * 2
                f.write(b'RIFF')
                f.write(struct.pack('<I', 36 + data_size))
                f.write(b'WAVE')
                f.write(b'fmt ')
                f.write(struct.pack('<IHHIIHH', 16, 1, 1, sample_rate,
                                    sample_rate * 2, 2, 16))
                f.write(b'data')
                f.write(struct.pack('<I', data_size))
                # 写正弦波采样
                for i in range(num_samples):
                    value = int(32767 * 0.3 * math.sin(2 * math.pi * frequency * i / sample_rate))
                    f.write(struct.pack('<h', value))

            return self._play_audio(wav_path) or True
        except Exception as e:
            print(f"[VoiceSynth] 测试音生成失败: {e}")
            return False

    @staticmethod
    def check_audio_devices() -> dict:
        """
        检查系统音频设备。

        Returns:
            {"playback": ["hw:0,0", ...], "capture": ["hw:1,0", ...],
             "espeak_installed": bool, "aplay_installed": bool}
        """
        result = {"playback": [], "capture": [],
                  "espeak_installed": False, "aplay_installed": False}

        # 检查 aplay
        try:
            r = subprocess.run(['aplay', '-l'], capture_output=True, text=True)
            result["aplay_installed"] = r.returncode == 0
            for line in r.stdout.split('\n'):
                if 'card' in line and 'device' in line:
                    # 解析 "card 0: ... device 0: ..." 格式
                    parts = line.strip().split(':')
                    if len(parts) >= 1:
                        result["playback"].append(line.strip())
        except FileNotFoundError:
            pass

        # 检查 arecord
        try:
            r = subprocess.run(['arecord', '-l'], capture_output=True, text=True)
            for line in r.stdout.split('\n'):
                if 'card' in line and 'device' in line:
                    result["capture"].append(line.strip())
        except FileNotFoundError:
            pass

        # 检查 espeak
        try:
            r = subprocess.run(['espeak', '--version'], capture_output=True, text=True)
            result["espeak_installed"] = r.returncode == 0
        except FileNotFoundError:
            pass

        return result

    def get_available_voices(self):
        """
        获取可用的语音列表

        Returns:
            list: 语音列表
        """
        try:
            result = subprocess.run(['espeak', '--voices'], capture_output=True, text=True)
            voices = []
            for line in result.stdout.strip().split('\n')[1:]:  # 跳过标题行
                if line.strip():
                    parts = line.split()
                    if len(parts) >= 4:
                        lang_code = parts[1]
                        voice_name = ' '.join(parts[3:])
                        voices.append({'code': lang_code, 'name': voice_name})
            return voices
        except Exception as e:
            print(f"获取语音列表错误: {e}")
            return []

# 使用示例
if __name__ == "__main__":
    synthesizer = VoiceSynthesizer()

    # 同步播放
    print("同步播放测试...")
    synthesizer.speak("欢迎使用智能储物柜系统", blocking=True)

    # 异步播放
    print("异步播放测试...")
    synthesizer.speak_async("请说出您需要的器件名称")
    synthesizer.speak_async("系统正在处理您的请求")

    import time
    time.sleep(5)