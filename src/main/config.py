# src/main/config.py

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

class Config:
    """配置管理类"""

    DEFAULT_CONFIG = {
        "system": {
            "name": "智能储物柜系统",
            "version": "2.0.0",
            "debug": False,
            "log_level": "INFO"
        },
        # ── LU-ASR01 硬件唤醒词模块 ──
        "lu_asr01": {
            "uart_port": "/dev/ttyUSB0",         # 实测: LU-ASR01 CH340→ttyUSB0
            "baudrate": 115200,                  # 必须与天问Block配置一致
            "timeout": 0.1,
            "enabled": True,
            "role": "wake_word_only",            # ★仅做唤醒词, 不做语音识别
            "wake_word_id": "wozai",
            "sleep_timeout": 15.0,
        },
        # ── 语音识别: Vosk (自然语言→文本) ──
        "voice": {
            "asr_model": "models/vosk-model-cn-0.22",  # Vosk中文大模型(2GB,识别率更高)
            "asr_sample_rate": 16000,
            "mic_device": "PCM2902",             # 实测: PCM2902 USB麦克风 (sounddevice按名称匹配)
            "audio_device": "plughw:3,0",         # 实测: PCM2902 card3 → plughw重采样到16kHz
            "tts_engine": "espeak",
            "language": "zh",
            "speed": 150,
            "pitch": 50,
            "listen_timeout": 8.0,               # 唤醒后最多听8秒
        },
        # ── 摄像头 ──
        "camera": {
            "device": "/dev/video0",
            "width": 640,
            "height": 480,
            "fps": 30,
            "face_detection_interval": 0.5,      # 检测间隔(秒)
            "face_recognition_threshold": 0.6,    # 欧氏距离阈值
        },
        "face_model": {
            "backend": "opencv_lbph",             # 首选opencv, 后续dlib_resnet
            "shape_predictor": "models/shape_predictor_68_face_landmarks.dat",
            "face_recognition": "models/dlib_face_recognition_resnet_model_v1.dat",
        },
        # ── 显示与触摸 ──
        "display": {
            "framebuffer": "/dev/fb0",
            "touch_device": "/dev/input/event2",  # 需在板子上 cat /proc/bus/input/devices 确认
            "width": 1024,
            "height": 600,
            "rotation": 0,
        },
        "ui": {
            "theme": "dark",
            "font_size": 14,
            "language": "zh_CN",
            "fullscreen": True,
            "gui_framework": "tkinter",           # Python自带, 后续可升级PyQt5
        },
        # ── 硬件控制（PCA9685 I2C 舵机驱动板 + GPIO 传感器）──
        "hardware": {
            "locker_count": 8,
            "pca9685": {
                "i2c_bus": 2,                    # RK3588 I2C2 (/dev/i2c-2)
                "i2c_address": 0x40,             # PCA9685 默认地址
                "pwm_freq": 50,                  # 舵机标准 50Hz
                "pwm_channels": [0, 1, 2, 3, 4, 5, 6, 7],  # 8路舵机对应PCA9685通道
            },
            "servo": {
                "open_angle": 90,
                "close_angle": 0,
                "open_duration_ms": 800,
                "min_pulse_us": 500,             # 0° 脉宽
                "max_pulse_us": 2500,            # 180° 脉宽
            },
            "door_sensor_pins": [5, 6, 7, 8, 9, 10, 11, 12],
            "led_pins": [24, 25, 26, 27, 28, 29, 30, 31],
            "nfc_device": "/dev/ttyUSB0"
        },
        # ── 数据库 ──
        "database": {
            "path": "data/components.db",
            "backup_path": "backups/",
            "backup_interval": 3600  # 1小时
        },
        # ── 安全 ──
        "security": {
            "admin_password": "admin123",
            "max_attempts": 3,
            "lock_time": 300  # 5分钟
        },
    }

    def __init__(self, config_file: str = "config.json"):
        """
        初始化配置

        Args:
            config_file: 配置文件路径
        """
        self.config_file = config_file
        self.config = self.DEFAULT_CONFIG.copy()
        self.load()

    def load(self) -> bool:
        """
        加载配置文件

        Returns:
            bool: 是否成功加载
        """
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    loaded_config = json.load(f)
                    self._deep_update(self.config, loaded_config)
                return True
            else:
                # 配置文件不存在，创建默认配置
                self.save()
                return True
        except Exception as e:
            print(f"加载配置文件错误: {e}")
            return False

    def save(self) -> bool:
        """
        保存配置文件

        Returns:
            bool: 是否成功保存
        """
        try:
            # 确保目录存在
            config_dir = os.path.dirname(self.config_file)
            if config_dir:
                Path(config_dir).mkdir(parents=True, exist_ok=True)

            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print(f"保存配置文件错误: {e}")
            return False

    def _deep_update(self, base: Dict, update: Dict) -> None:
        """深度更新字典"""
        for key, value in update.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                self._deep_update(base[key], value)
            else:
                base[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        """
        获取配置值

        Args:
            key: 配置键（支持点分隔，如 "system.name"）
            default: 默认值

        Returns:
            Any: 配置值
        """
        try:
            keys = key.split('.')
            value = self.config
            for k in keys:
                value = value[k]
            return value
        except (KeyError, TypeError):
            return default

    def set(self, key: str, value: Any, save_immediately: bool = False) -> bool:
        """
        设置配置值

        Args:
            key: 配置键（支持点分隔）
            value: 配置值
            save_immediately: 是否立即保存

        Returns:
            bool: 是否成功设置
        """
        try:
            keys = key.split('.')
            config_dict = self.config

            # 导航到最后一个键的父字典
            for k in keys[:-1]:
                if k not in config_dict or not isinstance(config_dict[k], dict):
                    config_dict[k] = {}
                config_dict = config_dict[k]

            # 设置值
            config_dict[keys[-1]] = value

            if save_immediately:
                return self.save()
            return True
        except Exception as e:
            print(f"设置配置错误: {e}")
            return False

    def get_all(self) -> Dict:
        """获取所有配置"""
        return self.config.copy()

    def reset_to_default(self) -> bool:
        """重置为默认配置"""
        self.config = self.DEFAULT_CONFIG.copy()
        return self.save()

# 全局配置实例
_config_instance: Optional[Config] = None

def get_config(config_file: str = "config.json") -> Config:
    """
    获取配置实例（单例模式）

    Args:
        config_file: 配置文件路径

    Returns:
        Config: 配置实例
    """
    global _config_instance
    if _config_instance is None:
        _config_instance = Config(config_file)
    return _config_instance