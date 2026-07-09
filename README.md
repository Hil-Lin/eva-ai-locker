# EVA AI 智能储物柜

基于 ELF 2 开发板（RK3588）的离线 AI 智能储物柜系统，支持语音/拼音自然语言搜索器件、人脸/NFC/密码三重身份验证、扫码归还，全程无需联网。

## 功能特性

- **AI 语义搜索**：规则匹配（~80%，<100ms）+ Qwen2-1.5B LLM 兜底（NPU 推理），用户说"5V稳压芯片"即可自动匹配器件
- **离线语音识别**：Vosk 2GB 中文大模型，流式增量解码，准确率 >90%
- **多重身份验证**：人脸识别（OpenCV LBPH）+ NFC 刷卡（PN532）+ 密码（SHA-256），3 次失败锁定
- **扫码归还**：扫码器自动感应，一次扫码自动识别器件并打开对应柜门，全程 <5 秒
- **全程离线运行**：所有 AI 推理、语音识别均在本地 NPU/CPU 完成，无需网络，保障数据隐私

## 硬件平台

| 组件 | 型号/规格 | 说明 |
|------|----------|------|
| 主控 | ELF 2 (RK3588) | 4×A76+4×A55, 6TOPS NPU, 8GB LPDDR4X |
| 显示 | 7寸 MIPI DSI | 1024×600, FT5x06 电容触控 |
| 电磁锁 | 4 路 | PCA9685 I2C PWM → MOSFET 驱动 |
| 摄像头 | OV13855 MIPI CSI | 640×480, 30fps |
| NFC | PN532 | CH340 USB-UART, ISO 14443 Type A |
| 扫码器 | 3550670018 | USB CDC-ACM, 自动感应 |
| 麦克风 | PCM2902 USB | 48kHz 采样 |

## 软件架构

```
GUI 层   — PyQt5 12 页触屏界面 (1024×600)
业务层   — 身份验证 (人脸/NFC/密码) + AI 引擎 (规则+LLM) + 语音交互 (Vosk)
基础层   — 硬件驱动 (PCA9685/摄像头/NFC/扫码器) + SQLite 数据库
硬件层   — ELF 2 RK3588 + 外设
```

## 项目结构

```
src/
├── ui/main_gui_qt.py         # PyQt5 主程序（12 页触屏 GUI）
├── database/db_manager.py    # SQLite 数据库（5 表 CRUD）
├── hardware/servo_driver.py  # PCA9685 I2C PWM 电磁锁驱动
├── ai/
│   ├── ai_engine.py          # 规则匹配 + LLM 双层语义引擎
│   └── rkllm_engine.py       # RKLLM NPU 推理封装
├── auth/
│   ├── auth_manager.py       # 登录验证、权限管理
│   ├── face_recognizer.py    # 人脸检测 + LBPH 识别
│   ├── camera.py             # MIPI/USB 双模摄像头
│   ├── nfc_reader.py         # PN532 NFC 读卡
│   └── barcode_scanner.py    # 条码扫描器驱动
├── voice/
│   ├── voice_recognizer.py   # Vosk 流式语音识别
│   └── voice_synthesizer.py  # 语音合成接口
└── main/
    ├── config.py             # 系统配置管理
    └── locker_cli.py         # CLI 命令行交互程序

scripts/                      # 板上辅助脚本
tests/                        # 测试文件
docs/                         # 设计文档
hardware/                     # 硬件 BOM 和原理图
```

## 快速开始

### 环境要求

- ELF 2 开发板 (RK3588) 或兼容硬件
- Ubuntu 22.04 (aarch64)
- Python 3.10+
- PyQt5
- OpenCV (contrib 模块, 含 LBPH)
- Vosk 模型 (`vosk-model-cn-0.22`)
- Qwen2-1.5B RKLLM 模型

### 安装

```bash
# 安装系统依赖
sudo apt install python3-pyqt5 python3-opencv libnfc-dev espeak

# 安装 Python 依赖
pip install pyqt5 opencv-contrib-python sounddevice numpy pyserial

# 下载 Vosk 中文模型
wget https://alphacephei.com/vosk/models/vosk-model-cn-0.22.zip
unzip vosk-model-cn-0.22.zip -d models/
```

### 运行

```bash
# 启动 GUI 主程序
cd /opt/smart-locker
PYTHONPATH=/opt/smart-locker python3 src/ui/main_gui_qt.py

# 或使用 CLI 命令行版本
PYTHONPATH=/opt/smart-locker python3 src/main/locker_cli.py
```

## 演示视频

[下载观看](https://github.com/Hil-Lin/eva-ai-locker/releases/download/v1.0.0/default.mp4)

## 许可证

GPL-3.0 License — 详见 [LICENSE](LICENSE) 文件
