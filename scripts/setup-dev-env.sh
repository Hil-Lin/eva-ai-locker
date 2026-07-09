#!/bin/bash
# EVA AI 智能储物柜 — 开发环境初始化脚本
# 适用平台: ELF 2 (RK3588) + Ubuntu 22.04 (aarch64)

set -e

echo "EVA AI 智能储物柜 — 开发环境初始化"
echo "====================================="

if [ "$(uname -m)" != "aarch64" ]; then
    echo "警告: 当前架构非 aarch64，此脚本针对 ELF 2 (RK3588) 设计"
fi

echo ""
echo "1. 安装系统依赖..."
sudo apt update
sudo apt install -y python3 python3-pip python3-pyqt5 python3-opencv
sudo apt install -y espeak libnfc-dev

echo ""
echo "2. 安装 Python 依赖..."
pip3 install --upgrade pip
pip3 install opencv-contrib-python sounddevice numpy pyserial

echo ""
echo "3. 检查关键外设..."
echo -n "  PCA9685 (I2C)... "
i2cdetect -y 2 2>/dev/null | grep -q "40" && echo "✓ 0x40" || echo "✗ 未检测到"
echo -n "  NFC (PN532)... "
[ -e /dev/ttyUSB0 ] && echo "✓ /dev/ttyUSB0" || echo "✗ 未连接"
echo -n "  扫码器... "
[ -e /dev/ttyACM0 ] && echo "✓ /dev/ttyACM0" || echo "✗ 未连接"
echo -n "  摄像头 (MIPI)... "
[ -e /dev/video11 ] && echo "✓ /dev/video11" || echo "✗ 未检测到"

echo ""
echo "4. 下载 Vosk 中文模型 (2GB)..."
MODEL_DIR="/opt/smart-locker/models"
if [ ! -d "$MODEL_DIR/vosk-model-cn-0.22" ]; then
    echo "  下载中..."
    wget -q --show-progress https://alphacephei.com/vosk/models/vosk-model-cn-0.22.zip
    unzip -q vosk-model-cn-0.22.zip -d "$MODEL_DIR/"
    rm vosk-model-cn-0.22.zip
    echo "  ✓ 完成"
else
    echo "  ✓ 已存在"
fi

echo ""
echo "====================================="
echo "开发环境初始化完成！"
echo ""
echo "运行主程序:"
echo "  cd /opt/smart-locker && PYTHONPATH=/opt/smart-locker python3 src/ui/main_gui_qt.py"
