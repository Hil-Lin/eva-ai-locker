"""
USB 摄像头驱动
==============

基于 OpenCV 的 USB UVC 摄像头封装，提供拍照和基本检测功能。

用法:
    cam = USBCamera(device="/dev/video0")
    cam.open()
    frame = cam.capture()        # RGB numpy array (HxWx3)
    cam.save_frame("/tmp/photo.jpg")
    cam.close()
"""

import os
import time
import subprocess
from typing import Optional, Tuple


class USBCamera:
    """USB UVC 摄像头驱动"""

    def __init__(self, device: str = "/dev/video0",
                 width: int = 640, height: int = 480, fps: int = 30):
        """
        Args:
            device: 摄像头设备路径
            width: 采集宽度
            height: 采集高度
            fps: 帧率
        """
        self.device = device
        self.width = width
        self.height = height
        self.fps = fps
        self._cap = None
        self.cam_type = 'auto'  # mipi/usb/auto — 用于判断是否需要 MIPI 预配置

    def open(self) -> bool:
        """
        打开摄像头。

        先尝试 OpenCV，若不可用则降级到 v4l2 + PIL。
        """
        # 方案1: OpenCV
        try:
            import cv2
            # MIPI 摄像头预配置: 用 v4l2-ctl 设置格式，避免 ISP 管线协商超时
            if self.cam_type in ("mipi", "auto") and self.device.startswith("/dev/video"):
                self._preconfig_mipi()
            # 如果设备是 /dev/videoX 格式，尝试用索引
            if self.device.startswith("/dev/video"):
                try:
                    idx = int(self.device.replace("/dev/video", ""))
                except ValueError:
                    idx = 0
                cap = cv2.VideoCapture(idx, cv2.CAP_V4L2)
            else:
                cap = cv2.VideoCapture(self.device, cv2.CAP_V4L2)

            if not cap.isOpened():
                print(f"[Camera] OpenCV 无法打开 {self.device}")
                return self._open_fallback()

            cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
            cap.set(cv2.CAP_PROP_FPS, self.fps)

            # 读一帧验证 — MIPI 管线启动后首帧可能稍慢，重试几次
            ret, frame = False, None
            for i in range(6):
                ret, frame = cap.read()
                if ret and frame is not None:
                    break
                time.sleep(0.15)
            if not ret or frame is None:
                cap.release()
                print("[Camera] 首帧读取失败")
                return self._open_fallback()

            actual_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            actual_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            print(f"[Camera] OpenCV 已打开 {self.device} ({actual_w}x{actual_h})")
            self._cap = cap
            self.width = actual_w
            self.height = actual_h
            return True

        except ImportError:
            print("[Camera] OpenCV 不可用，尝试 v4l2 方案")
            return self._open_fallback()
        except Exception as e:
            print(f"[Camera] 打开失败: {e}")
            return self._open_fallback()

    def _preconfig_mipi(self):
        """预先用 v4l2-ctl 设置 MIPI CSI 摄像头格式，避免 ISP 管线协商超时"""
        try:
            subprocess.run([
                'v4l2-ctl', '-d', self.device,
                '--set-fmt-video',
                f'width={self.width},height={self.height},pixelformat=UYVY'
            ], capture_output=True, timeout=5)
            print(f"[Camera] MIPI 预配置完成 {self.device} ({self.width}x{self.height} UYVY)")
        except Exception as e:
            print(f"[Camera] MIPI 预配置失败 (非致命): {e}")

    def _open_fallback(self) -> bool:
        """备用方案: 用 v4l2 + subprocess 抓帧"""
        # 检查设备是否存在
        if not os.path.exists(self.device):
            print(f"[Camera] 设备不存在: {self.device}")
            return False

        # 用 v4l2-ctl 检查
        import subprocess
        try:
            r = subprocess.run(['v4l2-ctl', '-d', self.device, '--list-formats'],
                             capture_output=True, text=True, timeout=5)
            if r.returncode == 0:
                print(f"[Camera] v4l2 设备已识别:")
                print(r.stdout[:200])
                self._use_v4l2 = True
                return True
        except FileNotFoundError:
            pass

        print("[Camera] 无可用方案，请安装 opencv-python-headless 或 v4l-utils")
        return False

    def capture(self) -> Optional[object]:
        """
        采集一帧 RGB 图像。

        Returns:
            numpy.ndarray (HxWx3, RGB) 或 None
        """
        if self._cap is not None:
            import cv2
            ret, frame = self._cap.read()
            if ret and frame is not None:
                # OpenCV 默认 BGR → 转 RGB
                return cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            return None

        # v4l2 fallback
        if getattr(self, '_use_v4l2', False):
            return self._capture_v4l2()

        return None

    def _capture_v4l2(self) -> Optional[object]:
        """用 v4l2-ctl 抓一帧 JPEG 然后用 PIL 解码"""
        import subprocess
        import tempfile
        try:
            tmp = tempfile.NamedTemporaryFile(suffix='.jpg', delete=False)
            tmp_path = tmp.name
            tmp.close()

            subprocess.run([
                'v4l2-ctl', '-d', self.device,
                '--set-fmt-video', f'width={self.width},height={self.height}',
                '--stream-mmap', '--stream-count=1',
                '--stream-to=' + tmp_path
            ], capture_output=True, timeout=5)

            if os.path.exists(tmp_path) and os.path.getsize(tmp_path) > 0:
                try:
                    from PIL import Image
                    import numpy as np
                    img = Image.open(tmp_path)
                    return np.array(img.convert('RGB'))
                except ImportError:
                    print("[Camera] PIL 不可用，无法解码 JPEG")
                finally:
                    os.unlink(tmp_path)
        except Exception as e:
            print(f"[Camera] v4l2 抓帧失败: {e}")
        return None

    def save_frame(self, path: str) -> bool:
        """采集一帧并保存到文件"""
        frame = self.capture()
        if frame is None:
            return False

        try:
            from PIL import Image
            import numpy as np
            img = Image.fromarray(frame)
            img.save(path)
            print(f"[Camera] 已保存: {path} ({img.size})")
            return True
        except ImportError:
            import cv2
            # frame 是 RGB，转 BGR 给 OpenCV 保存
            frame_bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
            cv2.imwrite(path, frame_bgr)
            print(f"[Camera] 已保存: {path}")
            return True

    def detect_faces(self, frame=None) -> list:
        """
        检测画面中的人脸（OpenCV Haar Cascade）。

        Args:
            frame: 图像数组，None 则自动采集一帧

        Returns:
            [(x, y, w, h), ...] 人脸边界框列表
        """
        if frame is None:
            frame = self.capture()
        if frame is None:
            return []

        try:
            import cv2
            # frame 是 RGB，转灰度
            if len(frame.shape) == 3 and frame.shape[2] == 3:
                gray = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)
            else:
                gray = frame

            cascade_path = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
            cascade = cv2.CascadeClassifier(cascade_path)
            faces = cascade.detectMultiScale(gray, scaleFactor=1.1,
                                             minNeighbors=5, minSize=(60, 60))
            return [(int(x), int(y), int(w), int(h)) for (x, y, w, h) in faces]
        except ImportError:
            print("[Camera] OpenCV 不可用，无法检测人脸")
            return []
        except Exception as e:
            print(f"[Camera] 人脸检测出错: {e}")
            return []

    @staticmethod
    def list_devices() -> list[str]:
        """列出所有可用的摄像头设备"""
        devices = []
        import glob
        for pattern in ["/dev/video*"]:
            for path in glob.glob(pattern):
                # 检查是否是 v4l2 设备
                try:
                    import subprocess
                    r = subprocess.run(['v4l2-ctl', '-d', path, '--info'],
                                     capture_output=True, text=True, timeout=3)
                    if 'Video Capture' in r.stdout or 'usb' in r.stdout.lower():
                        devices.append(path)
                except Exception:
                    # v4l2-ctl 不可用时，直接列出
                    if os.path.exists(path):
                        devices.append(path)
        return devices

    @property
    def is_open(self) -> bool:
        return self._cap is not None or getattr(self, '_use_v4l2', False)

    def close(self):
        """释放摄像头"""
        if self._cap is not None:
            self._cap.release()
            self._cap = None
            print("[Camera] 已释放")


# 兼容别名 — daemon/__init__.py 使用 Camera 导入
Camera = USBCamera

# ── 独立测试 ──
if __name__ == "__main__":
    import sys

    print("USB 摄像头测试")
    print(f"可用设备: {USBCamera.list_devices()}")

    dev = sys.argv[1] if len(sys.argv) > 1 else "/dev/video0"
    cam = USBCamera(device=dev)

    if not cam.open():
        print("摄像头打开失败")
        sys.exit(1)

    print("采集图像中...")
    frame = cam.capture()

    if frame is not None:
        print(f"图像尺寸: {frame.shape}")
        cam.save_frame("/tmp/camera_test.jpg")

        # 人脸检测
        faces = cam.detect_faces(frame)
        print(f"检测到 {len(faces)} 张人脸")
        for i, (x, y, w, h) in enumerate(faces):
            print(f"  人脸{i+1}: ({x}, {y}, {w}x{h})")
    else:
        print("采集失败")

    cam.close()
