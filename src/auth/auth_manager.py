#!/usr/bin/env python3
"""
权限管理模块
管理用户权限和身份验证
"""

from typing import Optional, Dict
from enum import IntEnum

class PermissionLevel(IntEnum):
    """权限等级"""
    GUEST = 0        # 访客
    STUDENT = 1      # 普通学生
    ADMIN = 2        # 管理员
    SUPER_ADMIN = 3  # 超级管理员

class AuthResult:
    """身份验证结果"""

    def __init__(self, success: bool, user_id: Optional[int] = None,
                 permission_level: int = 0, method: str = "",
                 message: str = ""):
        self.success = success
        self.user_id = user_id
        self.permission_level = permission_level
        self.method = method  # 'face', 'nfc', 'password'
        self.message = message

    def __str__(self):
        if self.success:
            return f"✅ 验证成功: 用户{self.user_id} ({self.method}), 权限:{self.permission_level}"
        else:
            return f"❌ 验证失败: {self.message}"

class AuthManager:
    """权限管理器"""

    def __init__(self, db_manager):
        self.db = db_manager
        self.face_recognizer = None
        self.nfc_reader = None

        # 验证失败计数（防暴力破解）
        self.failed_attempts = {}  # {ip_or_device: count}
        self.max_attempts = 3
        self.lockout_time = 300  # 5 分钟

    def set_face_recognizer(self, recognizer):
        """设置人脸识别器"""
        self.face_recognizer = recognizer
        print("[AuthManager] 人脸识别器已设置")

    def set_nfc_reader(self, reader):
        """设置 NFC 读卡器"""
        self.nfc_reader = reader
        print("[AuthManager] NFC 读卡器已设置")

    def authenticate_by_face(self, threshold: float = 80.0) -> AuthResult:
        """
        通过人脸识别验证

        Args:
            threshold: 置信度阈值

        Returns:
            AuthResult
        """
        if not self.face_recognizer:
            return AuthResult(False, message="人脸识别器未设置")

        print("\n[AuthManager] 🔍 人脸识别验证...")

        user_id = self.face_recognizer.recognize(threshold=threshold)

        if user_id is None:
            return AuthResult(False, message="人脸识别失败")

        # 查询用户信息
        user = self.db.get_user(user_id)
        if not user:
            return AuthResult(False, message="用户不存在")

        if user['account_status'] != 1:
            return AuthResult(False, message="账户已被禁用")

        permission_level = user['permission_level']
        if user['is_admin']:
            permission_level = PermissionLevel.ADMIN

        return AuthResult(
            success=True,
            user_id=user_id,
            permission_level=permission_level,
            method='face',
            message=f"欢迎, {user['name']}"
        )

    def authenticate_by_nfc(self, timeout: float = 10.0) -> AuthResult:
        """
        通过 NFC 校园卡验证

        Args:
            timeout: 超时时间

        Returns:
            AuthResult
        """
        if not self.nfc_reader:
            return AuthResult(False, message="NFC 读卡器未设置")

        print("\n[AuthManager] 🎫 NFC 刷卡验证...")

        card_id = self.nfc_reader.read_card_uid(timeout)

        if not card_id:
            return AuthResult(False, message="未读取到校园卡")

        # 查询用户
        user = self.db.get_user_by_card(card_id)

        if not user:
            return AuthResult(False, message="未注册的校园卡")

        if user['account_status'] != 1:
            return AuthResult(False, message="账户已被禁用")

        permission_level = user['permission_level']
        if user['is_admin']:
            permission_level = PermissionLevel.ADMIN

        return AuthResult(
            success=True,
            user_id=user['id'],
            permission_level=permission_level,
            method='nfc',
            message=f"欢迎, {user['name']}"
        )

    def authenticate_by_password(self, user_id: int, password: str) -> AuthResult:
        """
        通过密码验证（用于管理员）

        Args:
            user_id: 用户 ID
            password: 密码

        Returns:
            AuthResult
        """
        user = self.db.get_user(user_id)

        if not user:
            return AuthResult(False, message="用户不存在")

        if not user['is_admin']:
            return AuthResult(False, message="非管理员账户")

        if user['account_status'] != 1:
            return AuthResult(False, message="账户已被禁用")

        # 验证密码（实际应该使用哈希）
        if user['admin_password'] != password:
            return AuthResult(False, message="密码错误")

        return AuthResult(
            success=True,
            user_id=user_id,
            permission_level=PermissionLevel.ADMIN,
            method='password',
            message=f"管理员验证成功"
        )

    def authenticate(self, method: str = 'auto', **kwargs) -> AuthResult:
        """
        综合身份验证

        Args:
            method: 验证方法 ('auto', 'face', 'nfc', 'password')
            **kwargs: 其他参数

        Returns:
            AuthResult
        """
        if method == 'auto':
            # 自动选择：先尝试人脸，再尝试 NFC
            print("\n[AuthManager] 🔄 自动验证（人脸/NFC）...")

            # 尝试人脸
            result = self.authenticate_by_face()
            if result.success:
                return result

            # 尝试 NFC
            result = self.authenticate_by_nfc()
            if result.success:
                return result

            return AuthResult(False, message="人脸和 NFC 验证均失败")

        elif method == 'face':
            return self.authenticate_by_face(**kwargs)

        elif method == 'nfc':
            return self.authenticate_by_nfc(**kwargs)

        elif method == 'password':
            user_id = kwargs.get('user_id')
            password = kwargs.get('password')
            if user_id is None or password is None:
                return AuthResult(False, message="缺少 user_id 或 password")
            return self.authenticate_by_password(user_id, password)

        else:
            return AuthResult(False, message=f"不支持的验证方法: {method}")

    def check_permission(self, auth_result: AuthResult, required_level: int) -> bool:
        """
        检查权限

        Args:
            auth_result: 身份验证结果
            required_level: 所需权限等级

        Returns:
            是否有权限
        """
        if not auth_result.success:
            return False

        return auth_result.permission_level >= required_level

    def register_face(self, user_id: int) -> bool:
        """
        注册人脸

        Args:
            user_id: 用户 ID

        Returns:
            是否成功
        """
        if not self.face_recognizer:
            print("[AuthManager] ❌ 人脸识别器未设置")
            return False

        print(f"\n[AuthManager] 👤 注册用户 {user_id} 的人脸...")
        return self.face_recognizer.register_user(user_id)

    def register_nfc_card(self, user_id: int) -> bool:
        """
        注册 NFC 校园卡

        Args:
            user_id: 用户 ID

        Returns:
            是否成功
        """
        if not self.nfc_reader:
            print("[AuthManager] ❌ NFC 读卡器未设置")
            return False

        print(f"\n[AuthManager] 🎫 注册用户 {user_id} 的校园卡...")
        print("  请刷卡...")

        card_id = self.nfc_reader.read_card_uid(timeout=10)
        if not card_id:
            print("  ❌ 未读取到校园卡")
            return False

        # 检查卡片是否已被注册
        existing_user = self.db.get_user_by_card(card_id)
        if existing_user:
            print(f"  ⚠️ 卡片已被用户 {existing_user['id']} ({existing_user['name']}) 注册")
            return False

        # 更新用户记录
        success = self.db.update_user(user_id, card_id=card_id)
        if success:
            print(f"  ✅ 注册成功: 卡片 {card_id}")
            return True
        else:
            print(f"  ❌ 注册失败")
            return False

    def log_auth_attempt(self, user_id: int, method: str, success: bool, details: str = ""):
        """
        记录验证尝试

        Args:
            user_id: 用户 ID
            method: 验证方法
            success: 是否成功
            details: 详细信息
        """
        operation_type = "AUTH_SUCCESS" if success else "AUTH_FAILED"
        operation_details = f"{method} - {details}"

        self.db.add_admin_log(
            admin_id=user_id if success else 0,
            operation_type=operation_type,
            operation_subtype=method,
            operation_details=operation_details,
            success=1 if success else 0
        )


# 测试
if __name__ == '__main__':
    print("=" * 60)
    print("权限管理模块测试")
    print("=" * 60)

    import sys
    sys.path.insert(0, '/opt/smart-locker/src/database')
    from db_manager import DBManager

    db = DBManager()
    auth = AuthManager(db)

    print("\n权限等级:")
    for level in PermissionLevel:
        print(f"  {level.name}: {level.value}")

    print("\n✅ 模块加载成功")

    db.close()
