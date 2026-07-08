# 主控板原理图框架 (KiCad格式)

# 主控模块
- RK3588核心电路
  - 电源: 5V输入，通过PMIC生成多路电压
  - 内存: 8GB LPDDR4 (4颗)
  - 存储: 64GB eMMC
  - 时钟: 24MHz晶振
  - 复位电路

# 接口模块
- USB接口 ×2 (摄像头、调试)
- HDMI接口 (显示屏)
- 40针GPIO扩展口
  - I2C0: SCL(PA15), SDA(PA16) → STM32通信
  - UART2: TX(PA10), RX(PA9) → NFC模块
  - SPI1: CS(PB12), SCK(PB13), MISO(PB14), MOSI(PB15) → 备用通信
  - GPIO: 状态指示灯、按键

# 传感器接口
- USB Type-A接口: 摄像头
- UART接口: NFC读卡器 (3.3V电平)
- I2C预留接口: 温度传感器等

# 电源模块
- 输入: 5V/3A
- 输出:
  - 5V/2A (RK3588核心)
  - 3.3V/500mA (外设)
  - 1.8V/1A (DDR内存)
- 保护: 保险丝、TVS二极管、滤波电容