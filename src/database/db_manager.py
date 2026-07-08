#!/usr/bin/env python3
"""
数据库管理模块
管理器件、用户、借还记录等数据
"""

import sqlite3
import os
from typing import List, Dict, Optional
from datetime import datetime

class DBManager:
    """数据库管理器"""

    def __init__(self, db_path: str = '/opt/smart-locker/data/smart_locker.db'):
        self.db_path = db_path
        self._ensure_db_dir()
        self.conn = None
        self._connect()
        self._create_tables()

    def _ensure_db_dir(self):
        """确保数据库目录存在"""
        db_dir = os.path.dirname(self.db_path)
        if not os.path.exists(db_dir):
            os.makedirs(db_dir)

    def _connect(self):
        """连接数据库"""
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        print(f"[DBManager] 数据库连接成功: {self.db_path}")

    def _create_tables(self):
        """创建数据表"""
        cursor = self.conn.cursor()

        # 1. 器件信息表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS components (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                category TEXT,
                voltage REAL,
                current REAL,
                cabinet_id INTEGER,
                keywords TEXT,
                stock INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # 2. 用户信息表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                card_id TEXT UNIQUE,
                face_feature BLOB,
                permission_level INTEGER DEFAULT 1,
                is_admin INTEGER DEFAULT 0,
                admin_password TEXT,
                account_status INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # 3. 借还记录表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                component_id INTEGER,
                cabinet_id INTEGER,
                borrow_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                return_time TIMESTAMP,
                borrow_mode TEXT DEFAULT 'ai_assist',
                status TEXT DEFAULT 'borrowed',
                FOREIGN KEY (user_id) REFERENCES users(id),
                FOREIGN KEY (component_id) REFERENCES components(id)
            )
        ''')

        # 4. 条形码映射表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS barcode_mapping (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                barcode TEXT UNIQUE NOT NULL,
                component_id INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_scan_time TIMESTAMP,
                FOREIGN KEY (component_id) REFERENCES components(id)
            )
        ''')

        # 5. 管理员操作日志表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS admin_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_id INTEGER NOT NULL,
                operation_type TEXT NOT NULL,
                operation_subtype TEXT,
                operation_details TEXT,
                operation_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                ip_address TEXT,
                success INTEGER DEFAULT 1,
                error_message TEXT,
                affected_entity_type TEXT,
                affected_entity_id INTEGER,
                FOREIGN KEY (admin_id) REFERENCES users(id)
            )
        ''')

        self.conn.commit()
        print("[DBManager] 数据表创建完成")

    # ==================== 器件管理 ====================

    def add_component(self, name: str, category: str = None, voltage: float = None,
                     current: float = None, cabinet_id: int = None,
                     keywords: str = None, stock: int = 0) -> int:
        """添加器件"""
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO components (name, category, voltage, current, cabinet_id, keywords, stock)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (name, category, voltage, current, cabinet_id, keywords, stock))
        self.conn.commit()
        component_id = cursor.lastrowid
        print(f"[DBManager] 添加器件: {name} (ID: {component_id})")
        return component_id

    def get_component(self, component_id: int) -> Optional[Dict]:
        """获取器件信息"""
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM components WHERE id = ?', (component_id,))
        row = cursor.fetchone()
        if row:
            return dict(row)
        return None

    def get_all_components(self) -> List[Dict]:
        """获取所有器件"""
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM components ORDER BY id')
        return [dict(row) for row in cursor.fetchall()]

    def search_components(self, keyword: str = None, category: str = None,
                         voltage: float = None, limit: int = 10) -> List[Dict]:
        """搜索器件"""
        cursor = self.conn.cursor()
        query = 'SELECT * FROM components WHERE 1=1'
        params = []

        if keyword:
            query += ' AND (name LIKE ? OR keywords LIKE ?)'
            params.extend([f'%{keyword}%', f'%{keyword}%'])

        if category:
            query += ' AND category = ?'
            params.append(category)

        if voltage is not None:
            query += ' AND ABS(voltage - ?) < 0.5'
            params.append(voltage)

        query += ' ORDER BY stock DESC LIMIT ?'
        params.append(limit)

        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]

    def update_component(self, component_id: int, **kwargs) -> bool:
        """更新器件信息"""
        if not kwargs:
            return False

        cursor = self.conn.cursor()
        set_clause = ', '.join([f'{k} = ?' for k in kwargs.keys()])
        set_clause += ', updated_at = CURRENT_TIMESTAMP'
        values = list(kwargs.values()) + [component_id]

        cursor.execute(f'UPDATE components SET {set_clause} WHERE id = ?', values)
        self.conn.commit()
        return cursor.rowcount > 0

    def delete_component(self, component_id: int) -> bool:
        """删除器件"""
        cursor = self.conn.cursor()
        cursor.execute('DELETE FROM components WHERE id = ?', (component_id,))
        self.conn.commit()
        return cursor.rowcount > 0

    def get_components_for_ai(self) -> str:
        """获取器件列表供 AI 引擎使用"""
        components = self.get_all_components()
        lines = []
        for comp in components:
            line = f"{comp['id']}. {comp['name']}"
            if comp['category']:
                line += f" | {comp['category']}"
            if comp['voltage']:
                line += f" | {comp['voltage']}V"
            if comp['cabinet_id']:
                line += f" | 柜门{comp['cabinet_id']}"
            if comp['keywords']:
                line += f" | 关键词:{comp['keywords']}"
            lines.append(line)
        return '\n'.join(lines)

    # ==================== 用户管理 ====================

    def add_user(self, name: str, card_id: str = None, face_feature: bytes = None,
                permission_level: int = 1, is_admin: int = 0) -> int:
        """添加用户"""
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO users (name, card_id, face_feature, permission_level, is_admin)
            VALUES (?, ?, ?, ?, ?)
        ''', (name, card_id, face_feature, permission_level, is_admin))
        self.conn.commit()
        user_id = cursor.lastrowid
        print(f"[DBManager] 添加用户: {name} (ID: {user_id})")
        return user_id

    def get_user(self, user_id: int) -> Optional[Dict]:
        """获取用户信息"""
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,))
        row = cursor.fetchone()
        if row:
            return dict(row)
        return None

    def get_user_by_card(self, card_id: str) -> Optional[Dict]:
        """通过校园卡ID获取用户"""
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM users WHERE card_id = ?', (card_id,))
        row = cursor.fetchone()
        if row:
            return dict(row)
        return None

    def get_all_users(self) -> List[Dict]:
        """获取所有用户"""
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM users ORDER BY id')
        return [dict(row) for row in cursor.fetchall()]

    def update_user(self, user_id: int, **kwargs) -> bool:
        """更新用户信息"""
        if not kwargs:
            return False

        cursor = self.conn.cursor()
        set_clause = ', '.join([f'{k} = ?' for k in kwargs.keys()])
        set_clause += ', updated_at = CURRENT_TIMESTAMP'
        values = list(kwargs.values()) + [user_id]

        cursor.execute(f'UPDATE users SET {set_clause} WHERE id = ?', values)
        self.conn.commit()
        return cursor.rowcount > 0

    def delete_user(self, user_id: int) -> bool:
        """删除用户"""
        cursor = self.conn.cursor()
        cursor.execute('DELETE FROM users WHERE id = ?', (user_id,))
        self.conn.commit()
        return cursor.rowcount > 0

    # ==================== 借还记录管理 ====================

    def create_borrow_record(self, user_id: int, component_id: int,
                            cabinet_id: int, borrow_mode: str = 'ai_assist') -> int:
        """创建借用记录"""
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO records (user_id, component_id, cabinet_id, borrow_mode, status)
            VALUES (?, ?, ?, ?, 'borrowed')
        ''', (user_id, component_id, cabinet_id, borrow_mode))
        self.conn.commit()
        record_id = cursor.lastrowid
        print(f"[DBManager] 创建借用记录: 用户{user_id} 借用器件{component_id} (记录ID: {record_id})")
        return record_id

    def complete_return(self, record_id: int) -> bool:
        """完成归还"""
        cursor = self.conn.cursor()
        cursor.execute('''
            UPDATE records
            SET return_time = CURRENT_TIMESTAMP, status = 'returned'
            WHERE id = ?
        ''', (record_id,))
        self.conn.commit()
        return cursor.rowcount > 0

    def get_record(self, record_id: int) -> Optional[Dict]:
        """获取记录"""
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM records WHERE id = ?', (record_id,))
        row = cursor.fetchone()
        if row:
            return dict(row)
        return None

    def get_user_records(self, user_id: int, limit: int = 20) -> List[Dict]:
        """获取用户借还记录"""
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT * FROM records
            WHERE user_id = ?
            ORDER BY borrow_time DESC
            LIMIT ?
        ''', (user_id, limit))
        return [dict(row) for row in cursor.fetchall()]

    def get_borrowed_records(self) -> List[Dict]:
        """获取所有未归还记录"""
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT * FROM records
            WHERE status = 'borrowed'
            ORDER BY borrow_time DESC
        ''')
        return [dict(row) for row in cursor.fetchall()]

    # ==================== 条形码管理 ====================

    def add_barcode_mapping(self, barcode: str, component_id: int) -> int:
        """添加条形码映射"""
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO barcode_mapping (barcode, component_id)
            VALUES (?, ?)
        ''', (barcode, component_id))
        self.conn.commit()
        return cursor.lastrowid

    def get_component_by_barcode(self, barcode: str) -> Optional[Dict]:
        """通过条形码获取器件"""
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT c.* FROM components c
            JOIN barcode_mapping b ON c.id = b.component_id
            WHERE b.barcode = ?
        ''', (barcode,))
        row = cursor.fetchone()
        if row:
            # 更新最后扫描时间
            cursor.execute('''
                UPDATE barcode_mapping
                SET last_scan_time = CURRENT_TIMESTAMP
                WHERE barcode = ?
            ''', (barcode,))
            self.conn.commit()
            return dict(row)
        return None

    # ==================== 管理员日志 ====================

    def add_admin_log(self, admin_id: int, operation_type: str,
                     operation_subtype: str = None, operation_details: str = None,
                     success: int = 1, error_message: str = None,
                     affected_entity_type: str = None, affected_entity_id: int = None) -> int:
        """添加管理员操作日志"""
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO admin_logs
            (admin_id, operation_type, operation_subtype, operation_details,
             success, error_message, affected_entity_type, affected_entity_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (admin_id, operation_type, operation_subtype, operation_details,
              success, error_message, affected_entity_type, affected_entity_id))
        self.conn.commit()
        return cursor.lastrowid

    def get_admin_logs(self, admin_id: int = None, limit: int = 50) -> List[Dict]:
        """获取管理员操作日志"""
        cursor = self.conn.cursor()
        if admin_id:
            cursor.execute('''
                SELECT * FROM admin_logs
                WHERE admin_id = ?
                ORDER BY operation_time DESC
                LIMIT ?
            ''', (admin_id, limit))
        else:
            cursor.execute('''
                SELECT * FROM admin_logs
                ORDER BY operation_time DESC
                LIMIT ?
            ''', (limit,))
        return [dict(row) for row in cursor.fetchall()]

    # ==================== 数据库初始化 ====================

    def init_sample_data(self):
        """初始化示例数据"""
        print("[DBManager] 初始化示例数据...")

        # 添加示例器件
        sample_components = [
            ("LM7805", "稳压芯片", 5.0, 1.0, 1, "稳压,5V,线性稳压,电源芯片", 10),
            ("AMS1117-3.3", "稳压芯片", 3.3, 1.0, 2, "稳压,3.3V,LDO,电源芯片", 15),
            ("2N2222", "三极管", 40.0, 0.8, 3, "三极管,NPN,开关,放大", 50),
            ("STM32F103C8T6", "微控制器", 3.3, 0.05, 4, "单片机,ARM,Cortex-M3,MCU", 20),
            ("ESP32-WROOM-32", "无线模块", 3.3, 0.5, 5, "WiFi,蓝牙,物联网,无线", 12),
            ("1N4007", "二极管", 1000.0, 1.0, 6, "二极管,整流", 100),
            ("NE555", "集成电路", 5.0, 0.01, 7, "定时器,555,振荡器", 30),
            ("LM358", "集成电路", 5.0, 0.02, 8, "运放,运算放大器,双运放", 25),
        ]

        for comp in sample_components:
            self.add_component(*comp)

        # 添加示例用户
        self.add_user("管理员", "ADMIN001", None, 2, 1)
        self.add_user("张三", "STU001", None, 1, 0)
        self.add_user("李四", "STU002", None, 1, 0)

        print("[DBManager] 示例数据初始化完成")

    def close(self):
        """关闭数据库连接"""
        if self.conn:
            self.conn.close()
            print("[DBManager] 数据库连接已关闭")


# 测试
if __name__ == '__main__':
    print("=" * 60)
    print("数据库模块测试")
    print("=" * 60)

    # 创建数据库管理器
    db = DBManager('/tmp/test_smart_locker.db')

    # 初始化示例数据
    db.init_sample_data()

    # 测试器件查询
    print("\n--- 测试器件查询 ---")
    components = db.get_all_components()
    print(f"器件总数: {len(components)}")
    for comp in components[:3]:
        print(f"  {comp['id']}. {comp['name']} - {comp['category']}")

    # 测试 AI 接口
    print("\n--- 测试 AI 接口 ---")
    ai_text = db.get_components_for_ai()
    print(ai_text)

    # 测试搜索
    print("\n--- 测试搜索 ---")
    results = db.search_components(keyword="稳压")
    print(f"搜索'稳压': 找到 {len(results)} 个结果")

    # 测试用户查询
    print("\n--- 测试用户查询 ---")
    users = db.get_all_users()
    print(f"用户总数: {len(users)}")
    for user in users:
        print(f"  {user['id']}. {user['name']} (卡号: {user['card_id']})")

    # 测试借用记录
    print("\n--- 测试借用记录 ---")
    record_id = db.create_borrow_record(user_id=2, component_id=1, cabinet_id=1)
    print(f"创建借用记录: ID {record_id}")

    records = db.get_user_records(user_id=2)
    print(f"用户2的借还记录: {len(records)} 条")

    # 完成归还
    db.complete_return(record_id)
    print(f"完成归还: 记录 {record_id}")

    # 关闭数据库
    db.close()

    # 清理测试数据库
    import os
    os.remove('/tmp/test_smart_locker.db')

    print("\n✅ 数据库模块测试完成")
