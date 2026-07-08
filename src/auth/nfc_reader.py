#!/usr/bin/env python3
"""
NFC 读卡器模块
支持 PN532 NFC 模块（UART 接口）
"""

import serial
import time
from typing import Optional

class NFCReader:
    """NFC 读卡器（PN532 UART 模式）"""

    def __init__(self, port: str = '/dev/ttyS9', baudrate: int = 115200):
        self.port = port
        self.baudrate = baudrate
        self.serial = None

        # PN532 命令
        self.PN532_ACK = bytes([0x00, 0x00, 0xFF, 0x00, 0xFF, 0x00])
        self.PN532_WAKEUP = bytes([0x55, 0x55, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])

        print(f"[NFCReader] 初始化: {port} @ {baudrate}")

    def connect(self) -> bool:
        """连接串口"""
        try:
            self.serial = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=1
            )
            print(f"[NFCReader] ✅ 串口连接成功: {self.port}")

            # 唤醒 PN532
            self._wakeup()

            # 获取固件版本
            version = self.get_firmware_version()
            if version:
                print(f"[NFCReader] ✅ PN532 固件版本: {version}")
                return True
            else:
                print("[NFCReader] ⚠️ 无法获取固件版本，可能未连接 PN532")
                return False

        except serial.SerialException as e:
            print(f"[NFCReader] ❌ 串口连接失败: {e}")
            return False

    def _wakeup(self):
        """唤醒 PN532"""
        if self.serial:
            self.serial.write(self.PN532_WAKEUP)
            time.sleep(0.1)

    def _send_command(self, command: bytes) -> Optional[bytes]:
        """发送命令并接收响应"""
        if not self.serial:
            return None

        try:
            # 构造帧
            frame = self._build_frame(command)
            self.serial.write(frame)
            time.sleep(0.1)

            # 读取 ACK
            ack = self.serial.read(6)
            if ack != self.PN532_ACK:
                print(f"[NFCReader] ⚠️ ACK 错误: {ack.hex()}")
                return None

            # 读取响应
            response = self.serial.read(256)
            return self._parse_response(response)

        except Exception as e:
            print(f"[NFCReader] ❌ 通信错误: {e}")
            return None

    def _build_frame(self, command: bytes) -> bytes:
        """构造 PN532 帧"""
        length = len(command) + 1
        lcs = (~length + 1) & 0xFF

        frame = bytes([0x00, 0x00, 0xFF])
        frame += bytes([length, lcs])
        frame += bytes([0xD4])  # 主机到 PN532
        frame += command

        # 计算 DCS
        dcs = 0
        for b in frame[3:]:
            dcs += b
        dcs = (~dcs + 1) & 0xFF
        frame += bytes([dcs, 0x00])

        return frame

    def _parse_response(self, response: bytes) -> Optional[bytes]:
        """解析 PN532 响应"""
        if len(response) < 8:
            return None

        # 查找帧头
        start = response.find(bytes([0x00, 0x00, 0xFF]))
        if start < 0:
            return None

        # 提取数据
        length = response[start + 3]
        data = response[start + 6:start + 6 + length - 1]

        return data

    def get_firmware_version(self) -> Optional[str]:
        """获取固件版本"""
        # GetFirmwareVersion 命令
        command = bytes([0x02])
        response = self._send_command(command)

        if response and len(response) >= 4:
            ic = response[0]
            ver = response[1]
            rev = response[2]
            support = response[3]
            return f"IC:{ic:02X} Ver:{ver}.{rev} Support:{support}"

        return None

    def read_card_uid(self, timeout: float = 10.0) -> Optional[str]:
        """
        读取卡片 UID

        Args:
            timeout: 超时时间（秒）

        Returns:
            卡片 UID（十六进制字符串），超时返回 None
        """
        if not self.serial:
            print("[NFCReader] ❌ 未连接")
            return None

        print("[NFCReader] 等待刷卡...")
        start_time = time.time()

        while time.time() - start_time < timeout:
            # InListPassiveTarget 命令
            command = bytes([0x4A, 0x01, 0x00])  # 1 个目标，106 kbps type A
            response = self._send_command(command)

            if response and len(response) > 2:
                num_targets = response[0]
                if num_targets > 0:
                    # 提取 UID
                    uid_len = response[6]
                    uid_bytes = response[7:7 + uid_len]
                    uid = uid_bytes.hex().upper()

                    print(f"[NFCReader] ✅ 读取成功: {uid}")
                    return uid

            time.sleep(0.5)

        print("[NFCReader] ⏱️ 超时")
        return None

    def close(self):
        """关闭串口"""
        if self.serial:
            self.serial.close()
            print("[NFCReader] 串口已关闭")


# 测试
if __name__ == '__main__':
    print("=" * 60)
    print("NFC 读卡器测试")
    print("=" * 60)

    reader = NFCReader()

    if reader.connect():
        print("\n请刷卡...")
        uid = reader.read_card_uid(timeout=10)

        if uid:
            print(f"\n卡片 UID: {uid}")
        else:
            print("\n未读取到卡片")

        reader.close()
    else:
        print("\n❌ 无法连接 NFC 读卡器")
        print("提示: 检查 PN532 模块是否正确连接到 /dev/ttyS9")

    print("\n✅ 测试完成")
