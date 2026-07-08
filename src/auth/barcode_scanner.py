#!/usr/bin/env python3
"""
3550670018 扫码器驱动 — 基于 pyserial + ASCII 指令集
=====================================================

通过 USB 转串口 (CH340/CP2102) 与 ScanHome 扫码器通信。
发送 ASCII 指令触发扫描，读取串口返回的条码数据。

对标 NFCReader 的简洁设计，驱动层只管单次扫描，循环编排在业务层。

协议:
  - 通信方式: 串口 (USB虚拟串口)
  - 波特率: 115200 8N1
  - 指令集: ASCII (>!200000.^;99 格式)
  - 结束符: CR+LF (\r\n)

用法:
    scanner = BarcodeScanner(port="/dev/ttyUSB1")
    scanner.initialize()
    barcode = scanner.scan_once()  # 阻塞4s，返回条码或None
    scanner.close()
"""

import serial
import time
from typing import Optional


class BarcodeScanner:
    """3550670018 扫码器驱动 — pyserial + ASCII 指令"""

    # ASCII 指令常量
    CMD_SCAN = b'>!200000.^;99\r\n'        # 开始扫码 (4s超时)
    CMD_SCAN_NOTIMEOUT = b'>!200005.^;99\r\n'  # 开始扫码 (无超时)
    CMD_STOP = b'>!200001.^;99\r\n'        # 停止扫码
    CMD_NO_SLEEP = b'>!0010250.^;99\r\n'   # 不休眠 (持续供电)
    CMD_AUTO_SENSE = b'>!0010003.^;99\r\n'  # 自动感应模式 (持续监视，无需触发)
    CMD_END_CRLF = b'>!0010201.^;99\r\n'   # 结束符: 回车换行
    CMD_VOLUME_HIGH = b'>!001010100.^;99\r\n'  # 蜂鸣器音量高
    CMD_ACK_DISABLE = b'>!0010380.^;99\r\n' # 禁止指令应答 (简化通信)
    CMD_SAME_INTERVAL_0 = b'>!0010030.^;99\r\n'  # 同码间隔0ms (允许连续扫)

    # 默认串口参数
    DEFAULT_PORT = "/dev/ttyACM0"
    DEFAULT_BAUDRATE = 115200
    DEFAULT_TIMEOUT = 1.0  # 轮询间隔 (自动感应模式下越短越灵敏)

    def __init__(self, port: str = None, baudrate: int = None):
        """
        Args:
            port: 串口设备路径，默认 /dev/ttyUSB1
            baudrate: 波特率，默认 115200
        """
        self.port = port or self.DEFAULT_PORT
        self.baudrate = baudrate or self.DEFAULT_BAUDRATE
        self.ser: Optional[serial.Serial] = None
        self._debug = False

    def initialize(self) -> bool:
        """
        打开串口并发送初始化配置指令。

        配置序列 (对标 PDF 第四章操作步骤):
          1. 不休眠 (持续供电)
          2. 主机模式 (单次按键触发)
          3. 结束符 CR+LF
          4. 蜂鸣器高音量
          5. 禁止指令应答 (简化通信，不等待 ACK)

        Returns:
            是否成功
        """
        try:
            self.ser = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=0.1,
                write_timeout=1.0,
            )
            print(f"[BarcodeScanner] 串口已打开: {self.port} @ {self.baudrate}")

            # 清空缓冲区
            self.ser.reset_input_buffer()
            self.ser.reset_output_buffer()

            # 发送初始化指令序列
            init_cmds = [
                ("不休眠", self.CMD_NO_SLEEP),
                ("自动感应", self.CMD_AUTO_SENSE),
                ("结束符CRLF", self.CMD_END_CRLF),
                ("音量大", self.CMD_VOLUME_HIGH),
                ("禁止应答", self.CMD_ACK_DISABLE),
                ("同码无间隔", self.CMD_SAME_INTERVAL_0),
            ]

            for name, cmd in init_cmds:
                self._send_cmd(cmd)
                if self._debug:
                    print(f"  [BarcodeScanner] {name} 已发送")
                time.sleep(0.05)

            # 清空指令回显缓冲区（扫码器会 echo 收到的 ASCII 指令）
            self._drain_buffer()
            if self._debug:
                print("  [BarcodeScanner] 回显缓冲区已清空")

            print("[BarcodeScanner] ✅ 初始化完成")
            return True

        except serial.SerialException as e:
            print(f"[BarcodeScanner] ❌ 串口打开失败 ({self.port}): {e}")
            return False
        except Exception as e:
            print(f"[BarcodeScanner] ❌ 初始化异常: {e}")
            return False

    def _send_cmd(self, cmd: bytes):
        """发送指令到扫码器"""
        if self.ser and self.ser.is_open:
            self.ser.write(cmd)
            self.ser.flush()

    def _drain_buffer(self, wait: float = 0.3):
        """清空串口输入缓冲区（吃掉扫码器回显的指令数据）"""
        if not self.ser or not self.ser.is_open:
            return
        time.sleep(wait)
        self.ser.timeout = 0.1
        drained = b''
        try:
            while True:
                chunk = self.ser.read(1024)
                if not chunk:
                    break
                drained += chunk
        except Exception:
            pass
        if drained and self._debug:
            print(f"  [BarcodeScanner] 清空回显: {len(drained)} bytes")

    def scan_once(self, timeout: float = None) -> Optional[str]:
        """
        等待扫码器返回条码数据。

        自动感应模式下扫码器始终监视，有码自动读取并发送。
        只需阻塞等待串口数据即可，对标 NFC 的 readline() 模式。

        Args:
            timeout: 等待超时(秒)，默认 4.0

        Returns:
            条码字符串 (如 "CMP001")，或 None (超时/异常)
        """
        if not self.ser or not self.ser.is_open:
            print("[BarcodeScanner] ❌ 串口未打开")
            return None

        timeout = timeout or self.DEFAULT_TIMEOUT

        try:
            if self._debug:
                print(f"[BarcodeScanner] 等待扫码... (timeout={timeout}s)")

            self.ser.timeout = timeout
            line = self.ser.readline()

            if line:
                barcode = line.decode('utf-8', errors='replace').strip()
                barcode = barcode.replace('\r', '').replace('\n', '').strip()

                if barcode and self._debug:
                    print(f"[BarcodeScanner] 读到条码: {barcode}")

                return barcode if barcode else None

            return None

        except Exception as e:
            if self._debug:
                print(f"[BarcodeScanner] 读取异常: {e}")
            return None

    def stop_scan(self):
        """发送停止扫码指令"""
        self._send_cmd(self.CMD_STOP)

    def enable_debug(self, enabled: bool = True):
        """启用/禁用调试输出"""
        self._debug = enabled

    def close(self):
        """关闭串口"""
        if self.ser and self.ser.is_open:
            self.ser.close()
            print("[BarcodeScanner] 串口已关闭")

    @property
    def is_open(self) -> bool:
        return self.ser is not None and self.ser.is_open


# ── 独立测试 ──
if __name__ == "__main__":
    import sys

    port = sys.argv[1] if len(sys.argv) > 1 else "/dev/ttyUSB1"

    scanner = BarcodeScanner(port=port)
    scanner.enable_debug(True)

    print(f"3550670018 扫码器测试 — {port}")
    print()

    if not scanner.initialize():
        print("初始化失败，退出")
        sys.exit(1)

    print("\n请将条码对准扫码器... (Ctrl+C 退出)\n")

    try:
        while True:
            barcode = scanner.scan_once(timeout=4.0)
            if barcode:
                print(f"\n  >>> 条码: {barcode}\n")
            else:
                print("  (超时，重试...)")
    except KeyboardInterrupt:
        print("\n\n停止测试")
    finally:
        scanner.close()
