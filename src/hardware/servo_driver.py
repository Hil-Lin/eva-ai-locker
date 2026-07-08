"""
PCA9685 I2C 舵机驱动
====================

通过 I2C 总线控制 PCA9685 16通道 PWM 驱动板，驱动 SG90 舵机。

接线:
    PCA9685          RK3588 40pin
    ───────          ────────────
    VCC  ───→       3.3V (Pin1)
    GND  ───→       GND  (Pin6)
    SCL  ───→       I2C2_SCL (Pin5, GPIO3)
    SDA  ───→       I2C2_SDA (Pin3, GPIO2)
    5V端子 ←        外接 5V/3A 电源
    PWM0~7 ──→      8路 SG90 舵机信号线(橙/黄)

用法:
    driver = ServoDriver(i2c_bus=2, address=0x40)
    driver.initialize()
    driver.open_locker(0)    # 开第0路舵机(90°)
    driver.close_locker(0)   # 闭第0路舵机(0°)
    driver.shutdown()
"""

import time
import math
from typing import Optional, List


class ServoDriver:
    """
    PCA9685 I2C 16通道 PWM 舵机驱动。

    使用 smbus2 进行 I2C 通信，控制 SG90 舵机角度。
    """

    # PCA9685 寄存器
    __MODE1      = 0x00
    __MODE2      = 0x01
    __PRESCALE   = 0xFE
    __LED0_ON_L  = 0x06   # LED0 起始地址
    __ALLCALL     = 0x01  # MODE1 的 ALLCALL 位

    # SG90 舵机参数
    PWM_FREQ = 50                # Hz
    PERIOD_US = 1_000_000 / PWM_FREQ  # 20000 μs
    MIN_PULSE_US = 500           # 0° 脉宽
    MAX_PULSE_US = 2500          # 180° 脉宽

    def __init__(self, i2c_bus: int = 2, address: int = 0x40,
                 channels: List[int] = None):
        """
        Args:
            i2c_bus: I2C 总线编号 (RK3588 的 I2C2=2)
            address: PCA9685 I2C 地址 (默认0x40)
            channels: 使用的 PWM 通道列表 (默认0~7)
        """
        self.i2c_bus = i2c_bus
        self.address = address
        self.channels = channels or list(range(8))
        self._bus = None
        self._initialized = False

    # ══════════════════════════════════════════════════════
    # 初始化
    # ══════════════════════════════════════════════════════

    def initialize(self) -> bool:
        """
        初始化 I2C 通信 + PCA9685 配置。

        优先使用 smbus2，降级为 python-periphery，再降级为 sysfs 原始 I2C。
        """
        # 方案 1: smbus2
        if self._init_smbus2():
            self._apply_pwm_freq()
            self._initialized = True
            print(f"[ServoDriver] PCA9685 就绪 (I2C-{self.i2c_bus}, addr=0x{self.address:02X}, "
                  f"{len(self.channels)} 通道)")
            return True

        # 方案 2: python-periphery
        if self._init_periphery():
            self._apply_pwm_freq()
            self._initialized = True
            return True

        # 方案 3: 原生 sysfs I2C
        if self._init_sysfs_i2c():
            self._apply_pwm_freq()
            self._initialized = True
            return True

        print("[ServoDriver] 所有 I2C 方案均失败")
        return False

    def _init_smbus2(self) -> bool:
        try:
            from smbus2 import SMBus
            self._bus = SMBus(self.i2c_bus)
            # 测试通信
            self._bus.read_byte_data(self.address, self.__MODE1)
            print(f"[ServoDriver] smbus2 已连接")
            return True
        except ImportError:
            pass
        except Exception as e:
            print(f"[ServoDriver] smbus2 连接失败: {e}")
        return False

    def _init_periphery(self) -> bool:
        try:
            from periphery import I2C
            self._bus = I2C(f"/dev/i2c-{self.i2c_bus}")
            # 测试
            self._bus.transfer(self.address, [I2C.Message([self.__MODE1], read=True)])
            print(f"[ServoDriver] python-periphery 已连接")
            return True
        except ImportError:
            pass
        except Exception as e:
            print(f"[ServoDriver] periphery 连接失败: {e}")
        return False

    def _init_sysfs_i2c(self) -> bool:
        try:
            import os, fcntl, struct
            fd = os.open(f"/dev/i2c-{self.i2c_bus}", os.O_RDWR)
            # I2C_SLAVE = 0x0703
            fcntl.ioctl(fd, 0x0703, self.address)
            self._bus = fd  # 存 fd
            print(f"[ServoDriver] sysfs I2C 已打开 /dev/i2c-{self.i2c_bus}")
            return True
        except Exception as e:
            print(f"[ServoDriver] sysfs I2C 失败: {e}")
            self._bus = None
        return False

    def _i2c_write(self, reg: int, data: int):
        """统一 I2C 写接口"""
        if self._bus is None:
            return
        try:
            from smbus2 import SMBus
            if isinstance(self._bus, SMBus):
                self._bus.write_byte_data(self.address, reg, data)
                return
        except ImportError:
            pass
        try:
            from periphery import I2C
            if hasattr(self._bus, 'transfer'):
                msgs = [I2C.Message([reg, data])]
                self._bus.transfer(self.address, msgs)
                return
        except ImportError:
            pass
        # sysfs 方式
        import os
        try:
            os.write(self._bus, bytes([reg, data]))
        except Exception:
            pass

    def _i2c_read(self, reg: int) -> int:
        """统一 I2C 读接口"""
        if self._bus is None:
            return 0
        try:
            from smbus2 import SMBus
            if isinstance(self._bus, SMBus):
                return self._bus.read_byte_data(self.address, reg)
        except ImportError:
            pass
        try:
            from periphery import I2C
            if hasattr(self._bus, 'transfer'):
                msgs = [I2C.Message([reg]), I2C.Message([0], read=True)]
                self._bus.transfer(self.address, msgs)
                return msgs[1].data[0]
        except ImportError:
            pass
        # sysfs 方式
        import os
        try:
            os.write(self._bus, bytes([reg]))
            return os.read(self._bus, 1)[0]
        except Exception:
            return 0

    def _apply_pwm_freq(self):
        """设置 PCA9685 PWM 频率为 50Hz"""
        # 1. 进入睡眠模式
        mode1 = self._i2c_read(self.__MODE1)
        self._i2c_write(self.__MODE1, (mode1 & 0x7F) | 0x10)  # SLEEP=1

        # 2. 设置预分频器
        # prescale = round(osc_clock / (4096 * freq)) - 1
        # osc_clock = 25MHz (internal)
        prescale = round(25_000_000 / (4096 * self.PWM_FREQ)) - 1
        prescale = max(3, min(255, prescale))
        self._i2c_write(self.__PRESCALE, prescale)

        # 3. 唤醒
        self._i2c_write(self.__MODE1, mode1 & 0xEF)  # SLEEP=0
        time.sleep(0.005)

        # 4. 启用自动增量
        self._i2c_write(self.__MODE1, (mode1 & 0xEF) | 0x20)  # AUTOINC=1

    # ══════════════════════════════════════════════════════
    # 舵机控制
    # ══════════════════════════════════════════════════════

    def set_angle(self, channel: int, angle: float):
        """
        设置指定通道舵机角度。

        Args:
            channel: PWM 通道号 (0~15)
            angle: 角度 (0~180)
        """
        if not self._initialized or channel not in self.channels:
            return

        angle = max(0, min(180, angle))

        # 角度 → 脉宽(μs) → PCA9685 计数值
        pulse_us = self.MIN_PULSE_US + (angle / 180.0) * (self.MAX_PULSE_US - self.MIN_PULSE_US)
        # PCA9685: 每计数 = PERIOD_US / 4096
        count = int(pulse_us * 4096 / self.PERIOD_US)

        # 写 PCA9685 LED 寄存器
        led_base = self.__LED0_ON_L + channel * 4
        self._i2c_write(led_base, 0)           # ON_L
        self._i2c_write(led_base + 1, 0)       # ON_H
        self._i2c_write(led_base + 2, count & 0xFF)   # OFF_L
        self._i2c_write(led_base + 3, (count >> 8) & 0x0F)  # OFF_H

    def open_locker(self, channel: int):
        """开锁：舵机转 90°"""
        self.set_angle(channel, 90)
        time.sleep(0.8)
        self.stop(channel)

    def close_locker(self, channel: int):
        """闭锁：舵机转 0°"""
        self.set_angle(channel, 0)
        time.sleep(0.8)
        self.stop(channel)

    def stop(self, channel: int):
        """停止 PWM（设置 OFF=0 即占空比 0%，防堵转）"""
        if not self._initialized:
            return
        led_base = self.__LED0_ON_L + channel * 4
        self._i2c_write(led_base + 2, 0)  # OFF_L=0
        self._i2c_write(led_base + 3, 0)  # OFF_H=0

    def all_stop(self):
        """停止所有通道"""
        for ch in self.channels:
            self.stop(ch)

    def shutdown(self):
        """释放资源"""
        self.all_stop()
        self._bus = None
        self._initialized = False
        print("[ServoDriver] 已释放")


# ═══════════════════════════════════════════════════════
# 自测
# ═══════════════════════════════════════════════════════
if __name__ == "__main__":
    import sys

    bus = int(sys.argv[1]) if len(sys.argv) > 1 else 2
    addr = int(sys.argv[2], 16) if len(sys.argv) > 2 else 0x40

    print(f"PCA9685 舵机驱动测试")
    print(f"  I2C 总线: {bus}")
    print(f"  地址: 0x{addr:02X}")
    print(f"  命令: o0=开第0路, c0=关第0路, q=退出")
    print()

    driver = ServoDriver(i2c_bus=bus, address=addr)

    if not driver.initialize():
        print("初始化失败！请检查:")
        print("  1. PCA9685 接线: VCC/GND/SCL/SDA")
        print("  2. I2C 设备: i2cdetect -y " + str(bus))
        print("  3. 权限: sudo chmod 666 /dev/i2c-" + str(bus))
        sys.exit(1)

    print(f"可用通道: {driver.channels}")
    print()

    while True:
        try:
            cmd = input("> ").strip().lower()
            if cmd == 'q':
                break
            if cmd.startswith('o'):
                ch = int(cmd[1:])
                driver.open_locker(ch)
                print(f"  通道{ch}: 开锁 (90°)")
            elif cmd.startswith('c'):
                ch = int(cmd[1:])
                driver.close_locker(ch)
                print(f"  通道{ch}: 闭锁 (0°)")
            elif cmd.startswith('a'):
                angle = float(cmd[1:])
                driver.set_angle(0, angle)
                print(f"  通道0: {angle}°")
        except (EOFError, KeyboardInterrupt):
            break
        except Exception as e:
            print(f"  错误: {e}")

    driver.shutdown()
