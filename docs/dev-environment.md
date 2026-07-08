# 开发环境配置指南

## 系统要求
- 操作系统: Ubuntu 20.04 LTS 或更高
- 内存: 8GB RAM 以上
- 存储: 50GB 可用空间

## 已安装工具
1. **交叉编译工具链**
   - gcc-arm-linux-gnueabihf
   - g++-arm-linux-gnueabihf

2. **Buildroot依赖**
   - build-essential, cmake, pkg-config
   - libncurses5-dev, bc, rsync

3. **Python环境**
   - Python 3.8+
   - 虚拟环境: venv
   - 包: numpy, opencv-python, dlib, vosk, smbus2

4. **Qt5开发**
   - qt5-default
   - qtcreator (可选)

## 环境验证
运行以下命令验证环境:
```bash
# 检查交叉编译器
arm-linux-gnueabihf-gcc --version

# 检查Python
python3 --version
pip3 list | grep -E "numpy|opencv|dlib|vosk"

# 检查Buildroot
ls -la buildroot/
```

## 常见问题
1. **ARM工具链找不到**: 运行 `sudo apt install gcc-arm-linux-gnueabihf`
2. **Python包安装失败**: 使用国内镜像源 `pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple`
3. **Buildroot编译错误**: 确保所有依赖包已安装