#!/bin/bash
# scripts/setup-dev-env.sh

echo "智能储物柜系统开发环境设置脚本"
echo "================================="

# 检查Ubuntu版本
if [ ! -f /etc/os-release ]; then
    echo "错误: 仅支持Ubuntu系统"
    exit 1
fi

source /etc/os-release
if [ "$ID" != "ubuntu" ]; then
    echo "警告: 当前系统不是Ubuntu，可能不兼容"
fi

echo "1. 更新系统包管理器..."
sudo apt update
sudo apt upgrade -y

echo "2. 安装基本开发工具..."
sudo apt install -y build-essential git cmake pkg-config

echo "3. 安装ARM交叉编译工具链..."
sudo apt install -y gcc-arm-linux-gnueabihf g++-arm-linux-gnueabihf

echo "4. 安装Buildroot依赖..."
sudo apt install -y libncurses5-dev bc rsync cpio unzip wget

echo "5. 安装Python开发环境..."
sudo apt install -y python3 python3-pip python3-venv
pip3 install --upgrade pip

echo "6. 安装Qt5开发工具..."
sudo apt install -y qt5-default qtcreator

echo "7. 克隆Buildroot..."
if [ ! -d "buildroot" ]; then
    git clone https://github.com/buildroot/buildroot.git
    cd buildroot
    git checkout 2024.02  # 稳定版本
    cd ..
fi

echo "8. 设置Python虚拟环境..."
python3 -m venv venv
source venv/bin/activate
pip install numpy opencv-python dlib vosk

echo "开发环境设置完成！"
echo "请运行: source venv/bin/activate 激活Python环境"