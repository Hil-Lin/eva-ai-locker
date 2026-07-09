#!/usr/bin/env python3
"""
人脸识别模块
使用 OpenCV 进行人脸检测和识别
"""

import cv2
import numpy as np
import os
from typing import Optional, List, Tuple

class FaceRecognizer:
    """人脸识别器"""

    def __init__(self, model_dir: str = '/opt/smart-locker/data/face_models'):
        self.model_dir = model_dir
        os.makedirs(model_dir, exist_ok=True)

        # 加载人脸检测器
        cascade_path = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
        self.face_cascade = cv2.CascadeClassifier(cascade_path)

        # 人脸识别器（使用 LBPH 算法）
        self.recognizer = cv2.face.LBPHFaceRecognizer_create()

        # 用户标签映射
        self.label_map = {}  # {user_id: label}
        self.reverse_label_map = {}  # {label: user_id}

        # 持久化摄像头（避免反复 open/close 导致 ISP 驱动刷日志）
        self._cap = None

        # 尝试加载训练好的模型
        model_file = os.path.join(model_dir, 'face_recognizer.yml')
        label_file = os.path.join(model_dir, 'label_map.npy')

        if os.path.exists(model_file) and os.path.exists(label_file):
            self.recognizer.read(model_file)
            self.label_map = np.load(label_file, allow_pickle=True).item()
            self.reverse_label_map = {v: k for k, v in self.label_map.items()}
            print(f"[FaceRecognizer] 加载模型成功，已注册 {len(self.label_map)} 个用户")
        else:
            print("[FaceRecognizer] 未找到训练模型，需要先注册用户")

    def detect_face(self, image: np.ndarray) -> Optional[Tuple[int, int, int, int]]:
        """
        检测人脸

        Args:
            image: BGR 图像

        Returns:
            人脸边界框 (x, y, w, h)，如果未检测到返回 None
        """
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        faces = self.face_cascade.detectMultiScale(
            gray,
            scaleFactor=1.1,
            minNeighbors=5,
            minSize=(30, 30)
        )

        if len(faces) > 0:
            # 返回最大的人脸
            x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
            return (x, y, w, h)
        return None

    def _ensure_camera(self, camera_id: int = 0):
        """保持摄像头持续打开，避免反复 open/close 触发 ISP 日志刷屏"""
        if self._cap is None or not self._cap.isOpened():
            self._cap = cv2.VideoCapture(camera_id)
            if not self._cap.isOpened():
                print(f"[FaceRecognizer] 无法打开摄像头 {camera_id}")
                self._cap = None
                return False
            # 预热：丢弃前几帧等待自动曝光
            for _ in range(10):
                self._cap.read()
        return True

    def close_camera(self):
        """释放摄像头"""
        if self._cap is not None:
            self._cap.release()
            self._cap = None

    def capture_face_image(self, camera_id: int = 0) -> Optional[np.ndarray]:
        if not self._ensure_camera(camera_id):
            return None

        print("[FaceRecognizer] 正在检测人脸...")

        for attempt in range(30):
            ret, frame = self._cap.read()
            if not ret:
                continue

            face_box = self.detect_face(frame)
            if face_box:
                x, y, w, h = face_box
                face_roi = frame[y:y+h, x:x+w]
                gray_face = cv2.cvtColor(face_roi, cv2.COLOR_BGR2GRAY)
                gray_face = cv2.resize(gray_face, (100, 100))
                print(f"[FaceRecognizer] ✅ 检测到人脸 (尝试 {attempt + 1})")
                return gray_face

        print("[FaceRecognizer] ❌ 未检测到人脸")
        return None

    def register_user(self, user_id: int, num_samples: int = 20) -> bool:
        """
        注册新用户（采集人脸样本）

        Args:
            user_id: 用户 ID
            num_samples: 采集样本数量

        Returns:
            是否成功
        """
        print(f"\n[FaceRecognizer] 注册用户 {user_id}，请面对摄像头...")
        print(f"  将采集 {num_samples} 个人脸样本")
        print("  请保持头部正对摄像头，稍微转动头部\n")

        if not self._ensure_camera(0):
            print("[FaceRecognizer] 无法打开摄像头")
            return False

        # 分配新标签
        if user_id in self.label_map:
            label = self.label_map[user_id]
            print(f"  用户 {user_id} 已存在，更新人脸数据 (标签: {label})")
        else:
            label = len(self.label_map)
            self.label_map[user_id] = label
            self.reverse_label_map[label] = user_id
            print(f"  新用户 {user_id}，分配标签: {label}")

        samples_dir = os.path.join(self.model_dir, 'samples', f'user_{user_id}')
        os.makedirs(samples_dir, exist_ok=True)

        samples = []
        count = 0
        print("  开始采集样本...")

        while count < num_samples:
            ret, frame = self._cap.read()
            if not ret:
                continue

            face_box = self.detect_face(frame)
            if face_box:
                x, y, w, h = face_box
                face_roi = frame[y:y+h, x:x+w]
                gray_face = cv2.cvtColor(face_roi, cv2.COLOR_BGR2GRAY)
                gray_face = cv2.resize(gray_face, (100, 100))

                samples.append(gray_face)

                # 保存样本图像（用于调试）
                sample_file = os.path.join(samples_dir, f'sample_{count:03d}.jpg')
                cv2.imwrite(sample_file, gray_face)

                count += 1
                print(f"    样本 {count}/{num_samples}", end='\r')

        if len(samples) < 5:
            print(f"\n  ❌ 采集样本不足 ({len(samples)}/{num_samples})")
            return False

        print(f"\n  ✅ 采集完成，共 {len(samples)} 个样本")

        # 训练/更新识别器
        print("  训练识别器...")
        labels = [label] * len(samples)

        if len(self.label_map) == 1:
            # 第一个用户，直接训练
            self.recognizer.train(samples, np.array(labels))
        else:
            # 已有用户，需要重新训练所有数据
            all_samples, all_labels = self._load_all_samples()
            all_samples.extend(samples)
            all_labels.extend(labels)
            self.recognizer.train(all_samples, np.array(all_labels))

        # 保存模型
        model_file = os.path.join(self.model_dir, 'face_recognizer.yml')
        self.recognizer.save(model_file)
        np.save(os.path.join(self.model_dir, 'label_map.npy'), self.label_map)

        print("  ✅ 模型已保存")
        return True

    def _load_all_samples(self) -> Tuple[List[np.ndarray], List[int]]:
        """加载所有用户的样本"""
        samples = []
        labels = []

        samples_base = os.path.join(self.model_dir, 'samples')
        if not os.path.exists(samples_base):
            return samples, labels

        for user_dir in os.listdir(samples_base):
            user_id_str = user_dir.replace('user_', '')
            try:
                user_id = int(user_id_str)
                label = self.label_map.get(user_id)
                if label is None:
                    continue

                user_path = os.path.join(samples_base, user_dir)
                for sample_file in os.listdir(user_path):
                    if sample_file.endswith('.jpg'):
                        img = cv2.imread(os.path.join(user_path, sample_file), cv2.IMREAD_GRAYSCALE)
                        if img is not None:
                            samples.append(img)
                            labels.append(label)
            except:
                continue

        return samples, labels

    def recognize(self, camera_id: int = 0, threshold: float = 80.0) -> Optional[int]:
        """
        识别当前用户

        Args:
            camera_id: 摄像头 ID
            threshold: 置信度阈值（越小越严格）

        Returns:
            用户 ID，如果未识别返回 None
        """
        if not self.label_map:
            print("[FaceRecognizer] ❌ 没有注册的用户")
            return None

        face_image = self.capture_face_image(camera_id)
        if face_image is None:
            return None

        # 识别
        label, confidence = self.recognizer.predict(face_image)

        print(f"[FaceRecognizer] 识别结果: 标签 {label}, 置信度 {confidence:.2f}")

        if confidence < threshold:
            user_id = self.reverse_label_map.get(label)
            if user_id is not None:
                print(f"[FaceRecognizer] ✅ 识别成功: 用户 {user_id}")
                return user_id

        print(f"[FaceRecognizer] ❌ 识别失败（置信度 {confidence:.2f} > {threshold}）")
        return None

    def get_registered_users(self) -> List[int]:
        """获取已注册的用户列表"""
        return list(self.label_map.keys())


# 测试
if __name__ == '__main__':
    print("=" * 60)
    print("人脸识别模块测试")
    print("=" * 60)

    recognizer = FaceRecognizer()

    print("\n已注册用户:", recognizer.get_registered_users())

    # 注意：实际测试需要连接摄像头
    # recognizer.register_user(user_id=1, num_samples=20)
    # user_id = recognizer.recognize()

    print("\n✅ 模块加载成功")
