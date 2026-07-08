#!/usr/bin/env python3
"""
智能储物柜 — CLI 交互程序
=========================
借出/归还/注册/管理设置，循环驱动菜单。
密码登录(v1)，NFC/人脸留接口后补。

用法:
    python3 src/main/locker_cli.py              # 正常运行
    python3 src/main/locker_cli.py --init-db    # 初始化示例数据
    python3 src/main/locker_cli.py --no-tts     # 禁用语音播报
"""

import sys
import os
from pathlib import Path

# ── 路径设置 ──────────────────────────────────────────────
if os.path.exists('/opt/smart-locker'):
    BOARD_ROOT = '/opt/smart-locker'
    sys.path.insert(0, BOARD_ROOT)
    sys.path.insert(0, os.path.join(BOARD_ROOT, 'src/ai'))
    sys.path.insert(0, os.path.join(BOARD_ROOT, 'src/voice'))
    sys.path.insert(0, os.path.join(BOARD_ROOT, 'src/database'))
    sys.path.insert(0, os.path.join(BOARD_ROOT, 'src/main'))
else:
    BOARD_ROOT = str(Path(__file__).parent.parent.parent)
    sys.path.insert(0, BOARD_ROOT)
    sys.path.insert(0, os.path.join(BOARD_ROOT, 'src/ai'))
    sys.path.insert(0, os.path.join(BOARD_ROOT, 'src/voice'))
    sys.path.insert(0, os.path.join(BOARD_ROOT, 'src/database'))


class SmartLockerCLI:
    """智能储物柜 CLI 主程序"""

    def __init__(self, db_path=None, ai_model_path=None,
                 root_key='123456', use_tts=True):
        if db_path is None:
            db_path = '/opt/smart-locker/data/smart_locker.db'
        if ai_model_path is None:
            ai_model_path = ('/opt/smart-locker/models/'
                             'Qwen2-1.5B_W8A8_RK3588.rkllm')

        self.db_path = db_path
        self.ai_model_path = ai_model_path
        self.root_key = root_key
        self.use_tts = use_tts

        self.db = None
        self.ai = None
        self.tts = None

    # ══════════════════════════════════════════════════════
    # 生命周期
    # ══════════════════════════════════════════════════════

    def initialize(self) -> bool:
        """初始化数据库、AI引擎、可选TTS。返回是否成功。"""
        # ── 数据库 ──
        try:
            from db_manager import DBManager
            self.db = DBManager(db_path=self.db_path)
            # 验证连接
            self.db.get_all_components()
            self._migrate_database()
            print(f"✅ SQLite 数据库就绪 ({self.db_path})")
        except Exception as e:
            print(f"❌ 数据库连接失败: {e}")
            return False

        # ── AI 引擎 ──
        try:
            # 先尝试 ai_engine（板上部署的v6），再试 ai_engine_v6（本地）
            try:
                from ai_engine import AIEngineImpl, MatchResult, CandidateItem
            except ImportError:
                from ai_engine_v6 import AIEngineImpl, MatchResult, CandidateItem
            self.ai = AIEngineImpl()
            if self.ai.initialize(self.ai_model_path):
                print("✅ Qwen2 AI 引擎就绪")
            else:
                print("⚠️  AI LLM加载失败，使用规则匹配模式")
        except Exception as e:
            print(f"⚠️  AI引擎不可用 ({e})，将无法使用AI推荐借出")

        self._load_ai_catalog()

        # ── 语音合成 (可选) ──
        if self.use_tts:
            try:
                from voice_synthesizer import VoiceSynthesizer
                self.tts = VoiceSynthesizer(audio_device="hw:1,0")
                print("✅ eSpeak 语音合成就绪")
            except Exception as e:
                print(f"⚠️  语音合成不可用: {e}")

        # ── 统计 ──
        try:
            comps = self.db.get_all_components()
            users = self.db.get_all_users()
            print(f"📦 {len(comps)} 个器件, 👤 {len(users)} 个用户")
        except Exception:
            pass

        return True

    def shutdown(self):
        if self.ai:
            try:
                self.ai.shutdown()
            except Exception:
                pass
        if self.db:
            try:
                self.db.close()
            except Exception:
                pass

    def run(self):
        try:
            self._main_menu()
        except KeyboardInterrupt:
            print("\n\n再见！")
        except EOFError:
            print("\n退出")

    # ══════════════════════════════════════════════════════
    # 数据库迁移
    # ══════════════════════════════════════════════════════

    def _migrate_database(self):
        """给 users 表添加新列（如不存在）"""
        cursor = self.db.conn.cursor()
        cursor.execute("PRAGMA table_info(users)")
        existing = {row[1] for row in cursor.fetchall()}

        new_cols = [
            ("password",          "TEXT"),
            ("password_enabled",  "INTEGER DEFAULT 0"),
            ("nfc_enabled",       "INTEGER DEFAULT 0"),
            ("face_enabled",      "INTEGER DEFAULT 0"),
        ]
        for col_name, col_type in new_cols:
            if col_name not in existing:
                cursor.execute(
                    f"ALTER TABLE users ADD COLUMN {col_name} {col_type}")
        self.db.conn.commit()

    # ══════════════════════════════════════════════════════
    # 工具方法
    # ══════════════════════════════════════════════════════

    @staticmethod
    def _input(prompt: str) -> str:
        """读取用户输入，封装以统一行为"""
        try:
            return input(prompt).strip()
        except (EOFError, KeyboardInterrupt):
            return 'q'

    @staticmethod
    def _print_header(title: str):
        print()
        print("═" * 50)
        print(f"  {title}")
        print("═" * 50)

    def _speak(self, text: str):
        if self.tts:
            try:
                self.tts.speak_async(text)
            except Exception:
                pass

    def _load_ai_catalog(self):
        if not self.ai:
            return
        try:
            catalog = self.db.get_components_for_ai()
            if catalog:
                self.ai.set_catalog(catalog)
        except Exception:
            pass

    # ══════════════════════════════════════════════════════
    # 主菜单
    # ══════════════════════════════════════════════════════

    def _main_menu(self):
        while True:
            self._print_header("智能储物柜 v1")
            print("  1. 借器件")
            print("  2. 还器件")
            print("  3. 注册账号")
            print("  4. 设置")
            print("  q. 退出")
            print("─" * 50)

            choice = self._input("请选择: ").strip().lower()
            if choice in ('q', 'quit', '退出'):
                break
            elif choice == '1':
                self._borrow_flow()
            elif choice == '2':
                self._return_flow()
            elif choice == '3':
                self._register_flow()
            elif choice == '4':
                self._settings_flow()

    # ══════════════════════════════════════════════════════
    # 登录
    # ══════════════════════════════════════════════════════

    def _login_flow(self):
        """登录流程，返回 user dict 或 None（用户按b返回）"""
        while True:
            self._print_header("登录")
            print("  1. 密码登录")
            print("  2. NFC刷卡 (暂未开放)")
            print("  3. 人脸识别 (暂未开放)")
            print("  b. 返回")
            print("─" * 50)

            choice = self._input("请选择: ").strip().lower()
            if choice == 'b':
                return None
            elif choice == '1':
                user = self._login_by_password()
                if user:
                    return user
            elif choice in ('2', '3'):
                print("  该功能暂未开放，请选择其他方式")
                self._input("按 Enter 继续...")
            else:
                print("  无效选择")

    def _login_by_password(self):
        """密码登录，返回 user dict 或 None"""
        name = self._input("用户名: ").strip()
        if not name or name.lower() == 'b':
            return None

        # 查用户
        users = self.db.get_all_users()
        matched = [u for u in users if u.get('name', '') == name]
        if not matched:
            print(f"  用户 '{name}' 不存在")
            self._input("按 Enter 继续...")
            return None

        user = matched[0]

        # 检查是否启用了密码登录
        if not user.get('password_enabled'):
            print(f"  用户 '{name}' 未设置密码，请先注册或联系管理员补录登录方式")
            self._input("按 Enter 继续...")
            return None

        password = self._get_password("密码: ")
        if password is None:
            return None

        if user.get('password', '') != password:
            print("  密码错误")
            self._input("按 Enter 继续...")
            return None

        print(f"\n  ✅ 登录成功！欢迎 {name}")
        if user.get('is_admin'):
            print(f"  [管理员权限]")
        return user

    # ══════════════════════════════════════════════════════
    # 借出流程
    # ══════════════════════════════════════════════════════

    def _borrow_flow(self):
        self._print_header("借器件")
        print("  请先登录")
        user = self._login_flow()
        if user is None:
            return
        self._borrow_menu(user)

    def _borrow_menu(self, user):
        user_id = user['id']
        user_name = user.get('name', str(user_id))
        while True:
            self._print_header(f"借器件 — 用户: {user_name}")
            print("  1. AI对话推荐")
            print("  2. 直接选择")
            print("  b. 返回")
            print("─" * 50)

            choice = self._input("请选择: ").strip().lower()
            if choice == 'b':
                return
            elif choice == '1':
                self._borrow_ai_flow(user_id)
            elif choice == '2':
                self._borrow_direct_menu(user_id)
            else:
                print("  无效选择")

    # ── AI 推荐借出 ──

    def _borrow_ai_flow(self, user_id):
        if not self.ai:
            print("  ❌ AI引擎未加载，无法使用AI推荐")
            self._input("按 Enter 继续...")
            return

        comps = self.db.get_all_components()
        available = [c for c in comps if not self._is_component_borrowed(c['id'])]
        if not available:
            print("  ❌ 当前没有可借出的器件")
            self._input("按 Enter 继续...")
            return

        self._print_header("AI对话推荐")
        print("  请描述您需要的器件 (b 返回)")
        print("  提示: 长按空格键可触发语音输入(暂未实现)")
        print("─" * 50)

        query = self._input("> ")
        if not query or query.lower() == 'b':
            return

        print("\n  🤔 AI 匹配中...")
        try:
            result = self.ai.process_query(query)
        except Exception as e:
            print(f"  ❌ AI匹配失败: {e}")
            self._input("按 Enter 继续...")
            return

        # 无匹配
        if result.component_id is None and not result.is_ambiguous:
            print(f"\n  ❌ {result.response_text}")
            self._input("按 Enter 继续...")
            return

        # 歧义 — 多候选
        if result.is_ambiguous:
            print(f"\n  {result.response_text}")
            while True:
                choice = self._input("请选择序号 (b 返回): ").strip().lower()
                if choice == 'b':
                    return
                try:
                    idx = int(choice) - 1
                    if 0 <= idx < len(result.candidates):
                        c = result.candidates[idx]
                        self._borrow_confirm_and_execute(
                            user_id, c.component_id, c.cabinet_id,
                            c.component_name, 'ai_assist')
                        return
                    else:
                        print(f"  序号超出范围 (1-{len(result.candidates)})")
                except ValueError:
                    print("  请输入有效数字或 b 返回")

        # 单匹配
        else:
            print(f"\n  📢 {result.response_text}")
            confirm = self._input("确认借出? (y/n/b): ").strip().lower()
            if confirm == 'b':
                return
            if confirm in ('y', 'yes', '是', '确认', '1'):
                # 检查是否已被借走
                if self._is_component_borrowed(result.component_id):
                    print("  ❌ 该器件已被借出，请重新选择")
                    self._input("按 Enter 继续...")
                    return
                self._borrow_confirm_and_execute(
                    user_id, result.component_id, result.cabinet_id,
                    result.component_name, 'ai_assist')
            else:
                print("  👋 已取消")

    # ── 直接选择借出 ──

    def _borrow_direct_menu(self, user_id):
        while True:
            self._print_header("直接选择器件")
            print("  1. 按柜门浏览")
            print("  2. 按分类浏览")
            print("  b. 返回")
            print("─" * 50)

            choice = self._input("请选择: ").strip().lower()
            if choice == 'b':
                return
            elif choice == '1':
                self._borrow_by_cabinet(user_id)
            elif choice == '2':
                self._borrow_by_category(user_id)
            else:
                print("  无效选择")

    def _borrow_by_cabinet(self, user_id):
        comps = self.db.get_all_components()
        # 按 cabinet_id 分组
        cabinet_map = {}
        for c in comps:
            cid = c.get('cabinet_id')
            if cid is not None:
                cabinet_map.setdefault(cid, []).append(c)

        while True:
            self._print_header("按柜门选择")
            if not cabinet_map:
                print("  暂无已分配的柜门")
                self._input("按 Enter 继续...")
                return

            for cab in sorted(cabinet_map.keys()):
                for c in cabinet_map[cab]:
                    borrowed = self._is_component_borrowed(c['id'])
                    status = "[已借出]" if borrowed else "[可借]"
                    print(f"  {cab}号柜: {c['name']} | {c.get('category','')} {status}")
            print("  b. 返回")
            print("─" * 50)

            choice = self._input("请输入柜门号: ").strip().lower()
            if choice == 'b':
                return
            try:
                cab_num = int(choice)
                if cab_num in cabinet_map:
                    comp = cabinet_map[cab_num][0]
                    if self._is_component_borrowed(comp['id']):
                        print(f"  ❌ {comp['name']} 已被借出")
                        self._input("按 Enter 继续...")
                        continue
                    self._borrow_confirm_and_execute(
                        user_id, comp['id'], comp['cabinet_id'],
                        comp['name'], 'direct')
                    return
                else:
                    print(f"  柜门 {cab_num} 号不存在或未分配器件")
            except ValueError:
                print("  请输入有效数字")

    def _borrow_by_category(self, user_id):
        comps = self.db.get_all_components()
        categories = sorted(set(
            c.get('category', '未分类') for c in comps if c.get('category')))

        while True:
            self._print_header("按分类选择")
            if not categories:
                print("  暂无分类数据")
                self._input("按 Enter 继续...")
                return

            avail_counts = {}
            for cat in categories:
                avail_counts[cat] = sum(
                    1 for c in comps
                    if c.get('category') == cat
                    and not self._is_component_borrowed(c['id']))

            for i, cat in enumerate(categories, 1):
                print(f"  {i}. {cat} ({avail_counts[cat]}个可借)")
            print("  b. 返回")
            print("─" * 50)

            choice = self._input("请选择分类: ").strip().lower()
            if choice == 'b':
                return
            try:
                idx = int(choice) - 1
                if 0 <= idx < len(categories):
                    self._borrow_from_category(user_id, categories[idx])
                    return
                else:
                    print(f"  序号超出范围 (1-{len(categories)})")
            except ValueError:
                print("  请输入有效数字")

    def _borrow_from_category(self, user_id, category):
        comps = self.db.get_all_components()
        items = [c for c in comps if c.get('category') == category]

        while True:
            self._print_header(f"分类: {category}")
            for i, c in enumerate(items, 1):
                borrowed = self._is_component_borrowed(c['id'])
                status = "[已借出]" if borrowed else "[可借]"
                cabinet = c.get('cabinet_id', '?')
                print(f"  {i}. {c['name']} — {cabinet}号柜 {status}")
            print("  b. 返回")
            print("─" * 50)

            choice = self._input("请选择器件: ").strip().lower()
            if choice == 'b':
                return
            try:
                idx = int(choice) - 1
                if 0 <= idx < len(items):
                    comp = items[idx]
                    if self._is_component_borrowed(comp['id']):
                        print(f"  ❌ {comp['name']} 已被借出")
                        self._input("按 Enter 继续...")
                        continue
                    self._borrow_confirm_and_execute(
                        user_id, comp['id'], comp['cabinet_id'],
                        comp['name'], 'direct')
                    return
                else:
                    print(f"  序号超出范围 (1-{len(items)})")
            except ValueError:
                print("  请输入有效数字")

    def _borrow_confirm_and_execute(self, user_id, component_id,
                                     cabinet_id, component_name, mode):
        """确认借出: 写记录 + 模拟开柜"""
        try:
            record_id = self.db.create_borrow_record(
                user_id=user_id,
                component_id=component_id,
                cabinet_id=cabinet_id,
                borrow_mode=mode
            )
        except Exception as e:
            print(f"  ❌ 创建借用记录失败: {e}")
            self._input("按 Enter 继续...")
            return

        print()
        print("═" * 50)
        print(f"  📥 借出: {component_name}")
        print(f"  🚪 {cabinet_id}号柜门已打开 (模拟)")
        print(f"  📋 记录ID: {record_id}")
        print(f"  ⏰ 时间: {self._now()}")
        print("═" * 50)
        print("  ⚠️  柜门未实际安装，此为模拟开柜")
        self._speak(f'{component_name}，{cabinet_id}号柜已打开，请取走器件')
        self._input("按 Enter 确认已取走...")
        print("  ✅ 借出完成")

    # ══════════════════════════════════════════════════════
    # 归还流程
    # ══════════════════════════════════════════════════════

    def _return_flow(self):
        while True:
            self._print_header("还器件")
            print("  请扫描条形码 (暂未实现)")
            print("  或按 L 登录查看借用记录")
            print("  b. 返回")
            print("─" * 50)

            choice = self._input("> ").strip().lower()
            if choice == 'b':
                return
            elif choice == 'l':
                user = self._login_flow()
                if user is None:
                    continue
                self._return_show_borrowed(user['id'])
                # 归还完成后回到扫码/登录界面，不直接退回主菜单
            else:
                print("  条形码扫描功能暂未实现，请按 L 登录")

    def _return_show_borrowed(self, user_id):
        """显示用户借用列表，选择归还"""
        records = self.db.get_user_records(user_id, limit=50)
        borrowed = [r for r in records if r.get('status') == 'borrowed']

        if not borrowed:
            self._print_header("归还器件")
            print("  您当前没有未归还的器件")
            self._input("按 Enter 继续...")
            return

        while True:
            self._print_header("归还器件 — 您当前借出的器件")
            for i, rec in enumerate(borrowed, 1):
                comp = self.db.get_component(rec['component_id'])
                comp_name = comp['name'] if comp else f"ID:{rec['component_id']}"
                cab = rec.get('cabinet_id', '?')
                bt = rec.get('borrow_time', '?')
                print(f"  {i}. {comp_name} — {cab}号柜 — {bt}")

            print("  b. 返回")
            print("─" * 50)

            choice = self._input("请选择要归还的器件: ").strip().lower()
            if choice == 'b':
                return
            try:
                idx = int(choice) - 1
                if 0 <= idx < len(borrowed):
                    rec = borrowed[idx]
                    comp = self.db.get_component(rec['component_id'])
                    comp_name = comp['name'] if comp else f"ID:{rec['component_id']}"
                    cab = rec.get('cabinet_id', '?')

                    print(f"\n  归还 {comp_name} → {cab}号柜")
                    confirm = self._input("确认归还? (y/n): ").strip().lower()
                    if confirm in ('y', 'yes', '是'):
                        try:
                            self.db.complete_return(rec['id'])
                        except Exception as e:
                            print(f"  ❌ 归还失败: {e}")
                            self._input("按 Enter 继续...")
                            return
                        print(f"  🚪 {cab}号柜已打开，请放回 {comp_name}")
                        print("  ⏳ 等待关门检测... (模拟)")
                        print(f"  ✅ 归还成功")
                        self._speak(f'{comp_name}已归还到{cab}号柜')
                        self._input("按 Enter 继续...")
                        # 归还后刷新列表，继续归还其他器件
                        records = self.db.get_user_records(user_id, limit=50)
                        borrowed = [r for r in records if r.get('status') == 'borrowed']
                        if not borrowed:
                            print("  所有器件已归还完毕")
                            self._input("按 Enter 继续...")
                            return
                        continue
                    else:
                        print("  👋 已取消")
                        return
                else:
                    print(f"  序号超出范围 (1-{len(borrowed)})")
            except ValueError:
                print("  请输入有效数字")

    # ══════════════════════════════════════════════════════
    # 注册流程
    # ══════════════════════════════════════════════════════

    def _register_flow(self):
        self._print_header("注册账号")

        # ── 用户名 ──
        while True:
            name = self._input("设置用户名 (b 返回): ").strip()
            if not name or name.lower() == 'b':
                return
            # 检查重复
            users = self.db.get_all_users()
            if any(u.get('name', '') == name for u in users):
                print(f"  用户名 '{name}' 已存在，请换一个")
                continue
            break

        # ── 登录方式 (至少密码) ──
        self._print_header("选择登录方式 (至少一种)")
        print("  1. 设置密码 [必选]")
        print("  2. NFC刷卡 (暂未开放)")
        print("  3. 人脸识别 (暂未开放)")
        print("─" * 50)

        password = None
        while password is None:
            pwd = self._get_password("请设置密码 (至少1位): ")
            if pwd is None:
                return
            if len(pwd) < 1:
                print("  密码不能为空")
                continue
            pwd2 = self._get_password("请确认密码: ")
            if pwd2 is None:
                return
            if pwd != pwd2:
                print("  两次密码不一致，请重试")
                continue
            password = pwd

        # ── 写入数据库 ──
        try:
            user_id = self.db.add_user(name=name)
            self.db.update_user(user_id,
                                password=password,
                                password_enabled=1,
                                nfc_enabled=0,
                                face_enabled=0)
        except Exception as e:
            print(f"  ❌ 注册失败: {e}")
            self._input("按 Enter 继续...")
            return

        print()
        print(f"  ✅ 注册成功！")
        print(f"     用户名: {name}")
        print(f"     用户ID: {user_id}")
        print(f"     请牢记您的密码")
        self._input("按 Enter 继续...")

    # ══════════════════════════════════════════════════════
    # 设置 (管理员)
    # ══════════════════════════════════════════════════════

    def _settings_flow(self):
        if not self._settings_admin_auth():
            return
        self._settings_menu()

    def _settings_admin_auth(self) -> bool:
        """root密钥验证，3次机会"""
        for attempt in range(3):
            pwd = self._get_password("请输入管理员密钥 (b 返回): ")
            if pwd is None:
                return False
            if pwd == self.root_key:
                return True
            remaining = 2 - attempt
            if remaining > 0:
                print(f"  密钥错误，还剩 {remaining} 次机会")
            else:
                print("  验证失败次数过多，已锁定")
                self._input("按 Enter 继续...")
        return False

    def _settings_menu(self):
        while True:
            self._print_header("管理员设置")
            print("  1. 查看库存")
            print("  2. 借用状态总览")
            print("  3. 用户管理")
            print("  4. 管理员管理")
            print("  b. 返回主菜单")
            print("─" * 50)

            choice = self._input("请选择: ").strip().lower()
            if choice == 'b':
                return
            elif choice == '1':
                self._settings_view_inventory()
            elif choice == '2':
                self._settings_view_borrow_status()
            elif choice == '3':
                self._settings_user_management()
            elif choice == '4':
                self._settings_admin_management()
            else:
                print("  无效选择")

    def _settings_view_inventory(self):
        self._print_header("查看库存")
        comps = self.db.get_all_components()
        if not comps:
            print("  暂无器件")
        else:
            print(f"  {'ID':<4} {'名称':<25} {'分类':<12} {'柜门':<5} {'状态'}")
            print("  " + "─" * 60)
            for c in comps:
                borrowed = self._is_component_borrowed(c['id'])
                status = "已借出" if borrowed else "在库"
                print(f"  {c['id']:<4} {c['name']:<25} "
                      f"{c.get('category',''):<12} "
                      f"{c.get('cabinet_id','?'):<5} {status}")
            print(f"\n  共 {len(comps)} 个器件")
        self._input("按 Enter 继续...")

    def _settings_view_borrow_status(self):
        self._print_header("借用状态总览")
        records = self.db.get_borrowed_records()
        if not records:
            print("  当前没有未归还的借用记录")
        else:
            print(f"  {'记录ID':<7} {'借用人':<10} {'器件':<22} {'柜门':<5} {'借出时间'}")
            print("  " + "─" * 70)
            for r in records:
                user = self.db.get_user(r.get('user_id'))
                user_name = user['name'] if user else f"ID:{r['user_id']}"
                comp = self.db.get_component(r.get('component_id'))
                comp_name = comp['name'] if comp else f"ID:{r['component_id']}"
                print(f"  {r['id']:<7} {user_name:<10} {comp_name:<22} "
                      f"{r.get('cabinet_id','?'):<5} {r.get('borrow_time','?')}")
            print(f"\n  共 {len(records)} 条未归还记录")
        self._input("按 Enter 继续...")

    def _settings_user_management(self):
        while True:
            self._print_header("用户管理")
            users = self.db.get_all_users()
            if not users:
                print("  暂无用户")
                self._input("按 Enter 继续...")
                return

            for u in users:
                auth_methods = []
                if u.get('password_enabled'):
                    auth_methods.append('密码')
                if u.get('nfc_enabled'):
                    auth_methods.append('NFC')
                if u.get('face_enabled'):
                    auth_methods.append('人脸')
                auth_str = '+'.join(auth_methods) if auth_methods else '无'
                admin_str = ' [管理员]' if u.get('is_admin') else ''
                status_str = '启用' if u.get('account_status', 1) else '禁用'
                print(f"  {u['id']}. {u['name']} | {auth_str} | {status_str}{admin_str}")

            print("─" * 50)
            print("  1. 启用/禁用用户")
            print("  2. 删除用户")
            print("  b. 返回")
            print("─" * 50)

            choice = self._input("请选择: ").strip().lower()
            if choice == 'b':
                return
            elif choice == '1':
                uid_str = self._input("输入用户ID (b 返回): ").strip()
                if uid_str.lower() == 'b':
                    continue
                try:
                    uid = int(uid_str)
                    user = self.db.get_user(uid)
                    if not user:
                        print("  用户不存在")
                        continue
                    new_status = 0 if user.get('account_status', 1) else 1
                    self.db.update_user(uid, account_status=new_status)
                    label = "启用" if new_status else "禁用"
                    print(f"  用户 {user['name']} 已{label}")
                except ValueError:
                    print("  请输入有效数字")
            elif choice == '2':
                uid_str = self._input("输入要删除的用户ID (b 返回): ").strip()
                if uid_str.lower() == 'b':
                    continue
                try:
                    uid = int(uid_str)
                    user = self.db.get_user(uid)
                    if not user:
                        print("  用户不存在")
                        continue
                    confirm = self._input(
                        f"确认删除用户 '{user['name']}'? (输入名字确认): ").strip()
                    if confirm == user['name']:
                        self.db.delete_user(uid)
                        print(f"  用户 '{user['name']}' 已删除")
                    else:
                        print("  名称不匹配，已取消")
                except ValueError:
                    print("  请输入有效数字")
            self._input("按 Enter 继续...")

    def _settings_admin_management(self):
        while True:
            self._print_header("管理员管理")
            users = self.db.get_all_users()
            admins = [u for u in users if u.get('is_admin')]
            non_admins = [u for u in users if not u.get('is_admin')]

            print("  当前管理员:")
            if admins:
                for u in admins:
                    print(f"    {u['id']}. {u['name']}")
            else:
                print("    (无)")
            print()

            print("  1. 提升为管理员")
            print("  2. 撤销管理员")
            print("  3. 修改root密钥")
            print("  b. 返回")
            print("─" * 50)

            choice = self._input("请选择: ").strip().lower()
            if choice == 'b':
                return
            elif choice == '1':
                if not non_admins:
                    print("  没有可提升的用户")
                    self._input("按 Enter 继续...")
                    continue
                uid_str = self._input("输入要提升的用户ID (b 返回): ").strip()
                if uid_str.lower() == 'b':
                    continue
                try:
                    uid = int(uid_str)
                    user = self.db.get_user(uid)
                    if not user:
                        print("  用户不存在")
                        continue
                    if user.get('is_admin'):
                        print("  该用户已是管理员")
                        continue
                    self.db.update_user(uid, is_admin=1)
                    print(f"  {user['name']} 已提升为管理员")
                except ValueError:
                    print("  请输入有效数字")
            elif choice == '2':
                if not admins:
                    print("  没有可撤销的管理员")
                    self._input("按 Enter 继续...")
                    continue
                uid_str = self._input("输入要撤销的用户ID (b 返回): ").strip()
                if uid_str.lower() == 'b':
                    continue
                try:
                    uid = int(uid_str)
                    user = self.db.get_user(uid)
                    if not user:
                        print("  用户不存在")
                        continue
                    if not user.get('is_admin'):
                        print("  该用户不是管理员")
                        continue
                    self.db.update_user(uid, is_admin=0)
                    print(f"  {user['name']} 的管理员权限已撤销")
                except ValueError:
                    print("  请输入有效数字")
            elif choice == '3':
                old = self._get_password("当前root密钥: ")
                if old is None:
                    continue
                if old != self.root_key:
                    print("  密钥错误")
                    continue
                new = self._get_password("新root密钥: ")
                if new is None:
                    continue
                if len(new) < 1:
                    print("  密钥不能为空")
                    continue
                self.root_key = new
                print("  ✅ root密钥已更新")
            self._input("按 Enter 继续...")

    # ══════════════════════════════════════════════════════
    # 辅助查询
    # ══════════════════════════════════════════════════════

    def _is_component_borrowed(self, component_id: int) -> bool:
        """检查器件是否当前被借出"""
        try:
            records = self.db.get_borrowed_records()
            return any(
                r.get('component_id') == component_id
                and r.get('status') == 'borrowed'
                for r in records)
        except Exception:
            return False

    @staticmethod
    def _now() -> str:
        import time
        return time.strftime('%Y-%m-%d %H:%M:%S')

    @staticmethod
    def _get_password(prompt: str):
        """安全密码输入，降级为input()"""
        try:
            import getpass
            return getpass.getpass(prompt)
        except (ImportError, EOFError):
            return input(prompt).strip()

    # ══════════════════════════════════════════════════════
    # 入口
    # ══════════════════════════════════════════════════════

    @staticmethod
    def main():
        import argparse

        parser = argparse.ArgumentParser(description='智能储物柜 CLI')
        parser.add_argument('--db', default='/opt/smart-locker/data/smart_locker.db',
                            help='数据库路径')
        parser.add_argument('--model', default=None, help='AI模型路径')
        parser.add_argument('--root-key', default='123456', help='管理员root密钥')
        parser.add_argument('--no-tts', action='store_true', help='禁用语音播报')
        parser.add_argument('--init-db', action='store_true',
                            help='初始化示例数据')
        args = parser.parse_args()

        cli = SmartLockerCLI(
            db_path=args.db,
            ai_model_path=args.model,
            root_key=args.root_key,
            use_tts=not args.no_tts
        )

        if not cli.initialize():
            sys.exit(1)

        if args.init_db:
            try:
                cli.db.init_sample_data()
                # 给示例管理员设置密码
                users = cli.db.get_all_users()
                for u in users:
                    if u.get('is_admin'):
                        cli.db.update_user(u['id'],
                                           password='admin',
                                           password_enabled=1,
                                           nfc_enabled=0,
                                           face_enabled=0)
                        print(f"  [init] 管理员 '{u['name']}' 密码设为 admin")
                cli._load_ai_catalog()
                print("  [init] 示例数据初始化完成")
            except Exception as e:
                print(f"  [init] 示例数据初始化失败: {e}")

        try:
            cli.run()
        finally:
            cli.shutdown()


if __name__ == "__main__":
    SmartLockerCLI.main()
