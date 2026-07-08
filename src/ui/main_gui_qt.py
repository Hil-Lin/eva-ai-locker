#!/usr/bin/env python3
"""
智能储物柜 PyQt5 GUI v2
"""

import sys, os, time, subprocess, hashlib, json
sys.path.insert(0, '/opt/smart-locker')
sys.path.insert(0, '/opt/smart-locker/src/ai')

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QStackedWidget, QWidget, QLabel,
    QPushButton, QVBoxLayout, QHBoxLayout, QGridLayout, QScrollArea,
    QLineEdit, QTableWidget, QTableWidgetItem, QHeaderView, QTabWidget,
    QDialog, QMessageBox, QFrame, QSizePolicy, QAbstractItemView
)
from PyQt5.QtCore import Qt, pyqtSignal, QTimer
from PyQt5.QtGui import QColor

# ── DB & HW ──
from src.database.db_manager import DBManager
from src.hardware.servo_driver import ServoDriver

# ═══════════════════════════════════
W, H = 1024, 600
TITLE_H = 50

C_BG   = '#12100E'
C_BG2  = '#1A1714'
C_BG3  = '#211E1A'
C_TX   = '#E8E0D4'
C_TX2  = '#9C8E7C'
C_TX3  = '#6B5E4F'
C_AC   = '#D4705F'
C_JD   = '#6B9E7E'
C_BW   = '#7B8DB3'
C_BD   = '#302A22'

STYLE = f"""
QMainWindow, QWidget {{ background-color: {C_BG}; color: {C_TX}; }}
QPushButton {{ border: none; border-radius: 8px; font-size: 16px; }}
QLineEdit {{
    background: {C_BG3}; color: {C_TX}; border: 1px solid {C_BD};
    border-radius: 6px; padding: 8px; font-size: 16px;
}}
QTableWidget {{
    background: {C_BG2}; color: {C_TX}; border: 1px solid {C_BD};
    gridline-color: {C_BD}; font-size: 13px;
}}
QTableWidget::item {{ padding: 6px; }}
QTableWidget::item:selected {{ background: {C_BW}; }}
QHeaderView::section {{
    background: {C_BG3}; color: {C_TX2}; border: none; padding: 6px; font-weight: bold;
}}
QScrollArea {{ border: none; background: transparent; }}
QTabWidget::pane {{ border: 1px solid {C_BD}; background: {C_BG2}; }}
QTabBar::tab {{
    background: {C_BG3}; color: {C_TX2}; padding: 10px 20px;
    border: none; border-bottom: 2px solid transparent;
}}
QTabBar::tab:selected {{ color: {C_TX}; border-bottom: 2px solid {C_BW}; }}
QScrollBar:vertical {{ background: {C_BG}; width: 8px; }}
QScrollBar::handle:vertical {{ background: {C_BD}; border-radius: 4px; min-height: 20px; }}
"""

# ═══════════════════════════════════
# Widgets
# ═══════════════════════════════════

class TitleBar(QWidget):
    def __init__(self, title, parent=None, back_cb=None, user_name=None):
        super().__init__(parent)
        self.setFixedHeight(TITLE_H)
        self.setStyleSheet(f"background:{C_BG2}; border-bottom:1px solid {C_BD};")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 0, 8, 0)
        btn = QPushButton('← 返回')
        btn.setFixedSize(80, 36)
        btn.setStyleSheet(f"font-size:14px; color:{C_TX2}; background:transparent;")
        if back_cb:
            btn.clicked.connect(back_cb)
        layout.addWidget(btn)
        self.title_lbl = QLabel(title)
        self.title_lbl.setAlignment(Qt.AlignCenter)
        self.title_lbl.setStyleSheet(f"font-size:18px; font-weight:bold; color:{C_TX};")
        layout.addWidget(self.title_lbl, 1)
        self.user_lbl = QLabel(user_name if user_name else '')
        self.user_lbl.setFixedWidth(120)
        self.user_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.user_lbl.setStyleSheet(f"font-size:13px; color:{C_TX2}; padding-right:4px;")
        layout.addWidget(self.user_lbl)

    def set_user_name(self, name):
        self.user_lbl.setText(name if name else '')
    def set_title(self, title):
        self.title_lbl.setText(title)


class NumPad(QWidget):
    submitted = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QGridLayout(self)
        layout.setSpacing(6)
        btns = [
            ('1',0,0),('2',0,1),('3',0,2),
            ('4',1,0),('5',1,1),('6',1,2),
            ('7',2,0),('8',2,1),('9',2,2),
            ('⌫',3,0),('0',3,1),('✓',3,2),
        ]
        for txt, r, c in btns:
            btn = QPushButton(txt)
            btn.setMinimumSize(70, 50)
            if txt == '✓':
                btn.setStyleSheet(f"background:{C_JD}; color:#fff; font-size:20px;")
            elif txt == '⌫':
                btn.setStyleSheet(f"background:{C_AC}; color:#fff; font-size:16px;")
            else:
                btn.setStyleSheet(f"background:{C_BG3}; font-size:20px;")
            btn.clicked.connect(lambda checked, t=txt: self._on_key(t))
            layout.addWidget(btn, r, c)

    def _on_key(self, key):
        if key == '⌫': self.submitted.emit('BACK')
        elif key == '✓': self.submitted.emit('ENTER')
        else: self.submitted.emit(key)


class MsgOverlay(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setGeometry(0, 0, W, H)
        self.setStyleSheet("background: rgba(0,0,0,0.78);")
        self._container = QWidget(self)
        self._container.setGeometry(0, 0, W, 200)
        self._container.setStyleSheet("background: transparent;")
        cl = QVBoxLayout(self._container); cl.setAlignment(Qt.AlignCenter)
        self._icon = QLabel()
        self._icon.setAlignment(Qt.AlignCenter)
        self._icon.setStyleSheet("font-size:48px; background:transparent;")
        cl.addWidget(self._icon)
        self.label = QLabel()
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setStyleSheet("font-size:22px; color:#fff; background:transparent; padding:8px;")
        self.label.setWordWrap(True)
        cl.addWidget(self.label)
        self.hide()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.hide)

    def show_msg(self, text, duration=2000, icon=''):
        self._icon.setText(icon)
        self.label.setText(text)
        self.show(); self.raise_()
        if duration > 0: self._timer.start(duration)




# ═══════════════════════════════════
# MainWindow
# ═══════════════════════════════════

class MainWindow(QMainWindow):
    PAGE_HOME = 0
    PAGE_LOGIN = 1
    PAGE_BORROW_METHOD = 2
    PAGE_BORROW_DIRECT = 3
    PAGE_BORROW_AI = 4
    PAGE_BORROW_CATEGORY = 5
    PAGE_CATEGORY_DETAIL = 6
    PAGE_RETURN_METHOD = 7
    PAGE_RETURN_MANUAL = 8
    PAGE_RETURN_SCAN = 9
    PAGE_REGISTER = 10
    PAGE_ADMIN = 11

    def __init__(self):
        super().__init__()
        self.setWindowTitle('智能储物柜')
        self.setFixedSize(W, H)
        self.setStyleSheet(STYLE)

        # DB
        self.db = DBManager()

        # Servo
        self.servo = None
        try:
            self.servo = ServoDriver()
            self.servo.initialize()
            print('[Qt] Servo OK')
        except Exception as e:
            print(f'[Qt] Servo init failed: {e}')

        # TTS
        self.tts = None
        try:
            from src.voice.voice_synthesizer import VoiceSynthesizer
            self.tts = VoiceSynthesizer()
            print('[Qt] TTS OK')
        except Exception as e:
            print(f'[Qt] TTS init failed: {e}')

        # Vosk model — pre-load once for fast voice input. Prefer large model (2GB, much better CN accuracy)
        self._vosk_model = None
        try:
            from vosk import Model
            large = '/opt/smart-locker/models/vosk-model-cn-0.22'
            small = '/opt/smart-locker/models/vosk-model-small-cn-0.22'
            if os.path.exists(large):
                self._vosk_model = Model(large)
                print('[Qt] Vosk model OK (large, 2GB)')
            elif os.path.exists(small):
                self._vosk_model = Model(small)
                print('[Qt] Vosk model OK (small)')
            else:
                print('[Qt] Vosk model not found, voice disabled')
        except Exception as e:
            print(f'[Qt] Vosk init failed: {e}')

        # AI Engine
        self.ai_engine = None
        try:
            from ai_engine import AIEngineImpl
            self.ai_engine = AIEngineImpl()
            catalog = self._build_catalog()
            self.ai_engine.set_catalog(catalog)
            print('[Qt] AI Engine OK')
        except Exception as e:
            print(f'[Qt] AI Engine init failed: {e}')

        # Face daemon
        self._face_proc = None
        self._face_timer = None
        self._face_running = False
        self._start_face_daemon()

        # State
        self._logged_user = None
        self._return_context = False
        self._selected_category = None

        # Voice recording state
        self._recording = False
        self._record_proc = None
        self._record_timer = None
        self._record_countdown = None
        self._record_partial_timer = None
        self._record_seconds = 0
        self._record_recognizer = None
        self._record_text_partial = ''

        # NFC timer
        self.nfc_timer = QTimer()
        self.nfc_timer.timeout.connect(self._nfc_poll)

        # Overlay
        self.overlay = MsgOverlay(self)

        # Stack
        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)

        # Build all pages
        self._init_home()
        self._init_login()
        self._init_borrow_method()
        self._init_borrow_direct()
        self._init_borrow_ai()
        self._init_borrow_category()
        self._init_category_detail()
        self._init_return_method()
        self._init_return_manual()
        self._init_return_scan()
        self._init_register()
        self._init_admin()

        self.stack.currentChanged.connect(self._on_page_changed)
        self.stack.setCurrentIndex(0)

    # ── nav ──
    def closeEvent(self, event):
        if hasattr(self, '_face_proc') and self._face_proc and self._face_proc.poll() is None:
            try:
                with open('/tmp/face_auth_signal', 'w') as f:
                    f.write('quit')
                self._face_proc.wait(timeout=3)
            except Exception:
                try:
                    self._face_proc.kill()
                except Exception:
                    pass
        event.accept()

    def go(self, idx):
        self.stack.setCurrentIndex(idx)

    def go_home(self):
        self._logged_user = None
        self._return_context = False
        self._selected_category = None
        self._update_user_display()
        self.go(self.PAGE_HOME)

    def _update_user_display(self):
        name = self._logged_user['name'] if self._logged_user else ''
        for i in range(self.stack.count()):
            page = self.stack.widget(i)
            for bar in page.findChildren(TitleBar):
                bar.user_lbl.setText(name)

    def go_back(self):
        """Go home for most pages; context-aware"""
        self.go_home()

    def _on_page_changed(self, idx):
        # Stop recording if navigating away from AI page
        if self._recording and idx != self.PAGE_BORROW_AI:
            self._stop_recording()
        if idx == self.PAGE_BORROW_DIRECT:
            self._refresh_cabinet_grid()
        elif idx == self.PAGE_BORROW_AI:
            if self.ai_engine:
                self.ai_engine.set_catalog(self._build_catalog())
            self.ai_search_display.clear()
            self._clear_ai_candidates()
            self._clear_pinyin_candidates()
            self.ai_result.setText('输入拼音搜索器件，或按 🎤 语音')
        elif idx == self.PAGE_BORROW_CATEGORY:
            pass  # static
        elif idx == self.PAGE_CATEGORY_DETAIL:
            self._refresh_category_detail()
        elif idx == self.PAGE_RETURN_MANUAL:
            self._refresh_return_list()
        elif idx == self.PAGE_RETURN_SCAN:
            if hasattr(self, 'scan_timer'):
                is_borrow = hasattr(self, '_scan_context') and self._scan_context == 'borrow' and hasattr(self, '_borrow_comp')
                # Update TitleBar title
                page = self.stack.widget(idx)
                for bar in page.findChildren(TitleBar):
                    bar.set_title('扫码借出' if is_borrow else '扫码归还')
                if is_borrow:
                    self.scan_status.setText('请扫描取出器件的条码')
                    self.scan_detail.setText(f'{self._borrow_comp["name"]} - {self._borrow_comp["cabinet_id"]}号柜已打开')
                else:
                    self.scan_status.setText('等待扫码...')
                    self.scan_detail.setText('将条码对准扫码器')
                self.scan_timer.start(800)
        elif idx == self.PAGE_ADMIN:
            self._refresh_inventory()
            self._refresh_users()
            self._refresh_admin_table()
            self._refresh_logs()
        elif idx == self.PAGE_LOGIN:
            self.login_user_input.clear()
            self.login_pwd_display.clear()
            self._switch_login_mode('password')
            self.nfc_timer.start(300)
            if hasattr(self, 'login_kb_stack'):
                self.login_kb_stack.setCurrentIndex(0)
        else:
            if hasattr(self, 'scan_timer') and self.scan_timer.isActive():
                self.scan_timer.stop()
            self.nfc_timer.stop()
            if hasattr(self, '_face_timer') and self._face_timer and self._face_timer.isActive():
                self._face_timer.stop()
            self._face_running = False
            self.overlay.hide()
        # Clear borrow scan context when leaving scan page
        if idx != self.PAGE_RETURN_SCAN and hasattr(self, '_scan_context') and self._scan_context == 'borrow':
            self._scan_context = None
            self._borrow_comp = None

    # ── helpers ──
    def _toast(self, msg, dur=1500, icon=''):
        self.overlay.show_msg(msg, dur, icon)

    def _speak(self, text):
        if self.tts:
            try: self.tts.speak_async(text)
            except: pass

    def _scan_barcode(self):
        """尝试从扫码器读取一条条码，2秒超时"""
        try:
            import serial
            ser = serial.Serial('/dev/ttyACM0', 115200, timeout=0.1)
            t0 = time.time()
            buf = ''
            while time.time() - t0 < 3:
                b = ser.read(1)
                if b:
                    buf += b.decode('utf-8', errors='ignore')
                    if '\n' in buf or '\r' in buf:
                        ser.close()
                        return buf.strip().replace('\n', '').replace('\r', '')
            ser.close()
        except Exception:
            pass
        return None

    def _confirm_dialog(self, title, text, cb_yes):
        dlg = QDialog(self)
        dlg.setWindowTitle(title)
        dlg.setFixedWidth(580)
        dlg.setStyleSheet(f"background:{C_BG2};")
        layout = QVBoxLayout(dlg)
        layout.setSpacing(16)
        layout.setContentsMargins(24, 20, 24, 16)
        msg = QLabel(text)
        msg.setStyleSheet(f"color:{C_TX}; font-size:22px; padding:8px;")
        msg.setWordWrap(True)
        layout.addWidget(msg)
        btn_row = QHBoxLayout()
        btn_row.setSpacing(20)
        yes = QPushButton('是 (Yes)')
        yes.setFixedSize(240, 80)
        yes.setStyleSheet(f"background:{C_JD}; color:#fff; font-size:24px; font-weight:bold; border-radius:14px;")
        no = QPushButton('否 (No)')
        no.setFixedSize(240, 80)
        no.setStyleSheet(f"background:{C_AC}; color:#fff; font-size:24px; font-weight:bold; border-radius:14px;")
        btn_row.addWidget(yes); btn_row.addWidget(no)
        layout.addLayout(btn_row)
        yes.clicked.connect(dlg.accept); no.clicked.connect(dlg.reject)
        if dlg.exec_() == QDialog.Accepted:
            cb_yes()

    def _do_lock(self, cabinet):
        if self.servo:
            try:
                self.servo.lock_on(cabinet - 1)
                time.sleep(0.8)
                self.servo.lock_off(cabinet - 1)
            except Exception as e:
                print(f'[Qt] Lock error: {e}')

    # ═══════════════════════════════════
    # PAGE 0: Home
    # ═══════════════════════════════════
    def _init_home(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(40, 30, 40, 20)
        layout.setSpacing(16)

        title = QLabel('智能储物柜')
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet(f"font-size:28px; font-weight:bold; color:{C_TX};")
        title.setFixedHeight(60)
        layout.addWidget(title)

        for text, cb in [
            ('📦  借用器件', lambda: self._start_borrow()),
            ('🔄  归还器件', lambda: self.go(self.PAGE_RETURN_METHOD)),
            ('👤  用户注册', lambda: self.go(self.PAGE_REGISTER)),
        ]:
            card = QPushButton(text)
            card.setMinimumHeight(110)
            card.setStyleSheet(f"""
                QPushButton {{ background:{C_BG3}; border:1px solid {C_BD};
                    border-radius:12px; font-size:22px; font-weight:bold; color:{C_TX}; }}
                QPushButton:hover {{ border-color:{C_BW}; }}
            """)
            card.clicked.connect(cb)
            layout.addWidget(card)

        layout.addStretch()

        bottom = QHBoxLayout()
        bottom.addStretch()
        admin_btn = QPushButton('🔧 管理')
        admin_btn.setFixedSize(100, 40)
        admin_btn.setStyleSheet(f"font-size:13px; color:{C_TX2}; background:transparent; border:1px solid {C_BD}; border-radius:6px;")
        admin_btn.clicked.connect(self._admin_login_check)
        bottom.addWidget(admin_btn)
        layout.addLayout(bottom)

        self.stack.addWidget(page)

    def _start_borrow(self):
        self._return_context = False
        self.go(self.PAGE_LOGIN)

    def _admin_login_check(self):
        dlg = QDialog(self)
        dlg.setWindowTitle('管理员验证')
        dlg.setFixedSize(350, 400)
        dlg.setStyleSheet(f"background:{C_BG2};")
        layout = QVBoxLayout(dlg)
        layout.addWidget(QLabel('请输入管理员密钥'))
        pw = QLineEdit(); pw.setEchoMode(QLineEdit.Password); pw.setReadOnly(True)
        pw.setStyleSheet(f"background:{C_BG3}; color:{C_TX}; padding:8px; font-size:18px;")
        layout.addWidget(pw)
        numpad = NumPad()
        numpad.submitted.connect(lambda k: _on_key(k, pw))
        layout.addWidget(numpad)
        btn_row = QHBoxLayout()
        ok = QPushButton('确定'); ok.setMinimumHeight(44); ok.setStyleSheet(f"background:{C_BW}; color:#fff; padding:10px 20px; font-size:17px; border-radius:8px;")
        cancel = QPushButton('取消'); cancel.setMinimumHeight(44); cancel.setStyleSheet(f"background:{C_AC}; color:#fff; padding:10px 20px; font-size:17px; border-radius:8px;")
        btn_row.addWidget(ok); btn_row.addWidget(cancel)
        layout.addLayout(btn_row)
        ok.clicked.connect(dlg.accept); cancel.clicked.connect(dlg.reject)
        def _on_key(key, pw):
            if key == 'BACK': pw.setText(pw.text()[:-1])
            elif key == 'ENTER': pass
            else: pw.setText(pw.text() + key)
        if dlg.exec_() == QDialog.Accepted and pw.text() == '1':
            self.go(self.PAGE_ADMIN)
        elif dlg.result() == QDialog.Accepted:
            self._toast('密钥错误')

    # ═══════════════════════════════════
    # PAGE 1: Login
    # ═══════════════════════════════════
    def _init_login(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(40, 0, 40, 20)

        layout.addWidget(TitleBar('用户登录', back_cb=self.go_home))

        # Auth mode buttons (NFC 静默后台，不显示)
        mode_w = QWidget()
        mode_layout = QHBoxLayout(mode_w)
        self.login_btns = {}
        for mode, label in [('password','🔐 密码'), ('face','👤 人脸')]:
            btn = QPushButton(label)
            btn.setCheckable(True); btn.setMinimumHeight(50)
            btn.setStyleSheet(f"""
                QPushButton {{ background:{C_BG3}; font-size:16px; border-radius:8px; }}
                QPushButton:checked {{ background:{C_BW}; color:#fff; }}
            """)
            btn.clicked.connect(lambda checked, m=mode: self._switch_login_mode(m))
            self.login_btns[mode] = btn
            mode_layout.addWidget(btn)
        self.login_btns['password'].setChecked(True)
        layout.addWidget(mode_w)

        # Password widget
        self.login_pwd_widget = QWidget()
        pwd_layout = QVBoxLayout(self.login_pwd_widget); pwd_layout.setSpacing(12)
        self.login_user_input = QLineEdit(); self.login_user_input.setPlaceholderText('用户名'); self.login_user_input.setReadOnly(True); self.login_user_input.setFixedHeight(45)
        pwd_layout.addWidget(self.login_user_input)
        self.login_pwd_display = QLineEdit(); self.login_pwd_display.setPlaceholderText('密码')
        self.login_pwd_display.setEchoMode(QLineEdit.Password); self.login_pwd_display.setFixedHeight(45); self.login_pwd_display.setReadOnly(True)
        pwd_layout.addWidget(self.login_pwd_display)

        # 键盘区域：字母 / 数字切换
        self.login_kb_stack = QStackedWidget()
        self.login_kb_stack.setFixedHeight(200)

        lw = QWidget(); lg = QGridLayout(lw); lg.setSpacing(4)
        qwerty = ['QWERTYUIOP', 'ASDFGHJKL', 'ZXCVBNM']
        for r, keys in enumerate(qwerty):
            for c, ch in enumerate(keys):
                btn = QPushButton(ch); btn.setMinimumHeight(36)
                btn.setStyleSheet(f"background:{C_BG3}; font-size:15px; border-radius:4px;")
                btn.clicked.connect(lambda checked, ch=ch: self._on_login_letter(ch))
                lg.addWidget(btn, r, c)
        bk = QPushButton('⌫'); bk.setMinimumHeight(36)
        bk.setStyleSheet(f"background:{C_AC}; color:#fff; font-size:14px; border-radius:4px;")
        bk.clicked.connect(lambda: self._on_login_letter('BACK'))
        lg.addWidget(bk, 2, 8, 1, 2)
        sp = QPushButton('空格'); sp.setMinimumHeight(36)
        sp.setStyleSheet(f"background:{C_BG3}; font-size:14px; border-radius:4px;")
        sp.clicked.connect(lambda: self._on_login_letter(' '))
        lg.addWidget(sp, 3, 0, 1, 5)
        nt = QPushButton('🔢 数字'); nt.setMinimumHeight(36)
        nt.setStyleSheet(f"background:{C_BW}; color:#fff; font-size:14px; border-radius:4px;")
        nt.clicked.connect(lambda: self.login_kb_stack.setCurrentIndex(1))
        lg.addWidget(nt, 3, 5, 1, 5)
        self.login_kb_stack.addWidget(lw)

        nw = QWidget(); nl = QVBoxLayout(nw); nl.setContentsMargins(0,0,0,0)
        numpad = NumPad(); numpad.submitted.connect(self._on_login_key)
        nl.addWidget(numpad)
        lt = QPushButton('🔤 字母'); lt.setFixedHeight(30)
        lt.setStyleSheet(f"background:{C_BW}; color:#fff; font-size:14px; border-radius:4px;")
        lt.clicked.connect(lambda: self.login_kb_stack.setCurrentIndex(0))
        nl.addWidget(lt)
        self.login_kb_stack.addWidget(nw)

        pwd_layout.addWidget(self.login_kb_stack)
        layout.addWidget(self.login_pwd_widget)

        # 字段点击切换键盘
        self.login_user_input.mousePressEvent = lambda e: self.login_kb_stack.setCurrentIndex(0)
        self.login_pwd_display.mousePressEvent = lambda e: self.login_kb_stack.setCurrentIndex(1)

        # Face widget
        self.login_face_widget = QWidget()
        face_l = QVBoxLayout(self.login_face_widget)
        face_btn = QPushButton('👤 启动人脸识别')
        face_btn.setMinimumHeight(90)
        face_btn.setStyleSheet(f"background:{C_BW}; color:#fff; font-size:20px; border-radius:12px;")
        face_btn.clicked.connect(self._start_face_auth)
        face_l.addWidget(face_btn)
        self.login_face_widget.hide()
        layout.addWidget(self.login_face_widget)

        self.stack.addWidget(page)

    def _switch_login_mode(self, mode):
        for m, btn in self.login_btns.items():
            btn.setChecked(m == mode)
        self.login_pwd_widget.setVisible(mode == 'password')
        self.login_face_widget.setVisible(mode == 'face')
        self.overlay.hide()
        if mode == 'face':
            self._start_face_auth()

    def _nfc_poll(self):
        try:
            result = subprocess.run(
                ['nfc-list', '-v'], capture_output=True, text=True, timeout=2
            )
            out = result.stdout
            # nfc-list -v 输出格式: "UID (NFCID1): 42  68  32  07"
            for line in out.split('\n'):
                if 'UID' in line and 'NFCID' in line:
                    uid = line.split(':')[-1].strip().replace(' ', '').upper()
                    if uid and len(uid) >= 8:
                        self._on_nfc_card(uid)
                        return
        except Exception:
            pass

    def _on_login_letter(self, ch):
        inp = self.login_user_input
        if ch == 'BACK': inp.setText(inp.text()[:-1])
        else: inp.setText(inp.text() + ch)

    def _on_login_key(self, key):
        if key == 'BACK':
            cur = self.login_pwd_display.text()
            self.login_pwd_display.setText(cur[:-1])
        elif key == 'ENTER':
            self._do_password_login()
        else:
            self.login_pwd_display.setText(self.login_pwd_display.text() + key)

    def _do_password_login(self):
        username = self.login_user_input.text().strip()
        password = self.login_pwd_display.text()
        if not username:
            self._toast('请输入用户名'); return
        users = self.db.get_all_users()
        user = None
        for u in users:
            if u['name'] == username:
                user = u; break
        if not user:
            self._toast('用户不存在'); return
        stored_pw = user.get('password') or user.get('admin_password') or ''
        if hashlib.sha256(password.encode()).hexdigest() == stored_pw or password == stored_pw:
            self._on_login_success(user)
        else:
            self._toast('密码错误')

    def _on_nfc_card(self, uid):
        self.nfc_timer.stop()
        self.overlay.hide()
        user = self.db.get_user_by_card(uid)
        if user:
            self._on_login_success(user)
        else:
            self._toast(f'未注册卡片: {uid}', 2500)
            QTimer.singleShot(2500, lambda: self.nfc_timer.start(300))

    def _start_face_daemon(self):
        # 先优雅关闭旧守护进程
        if hasattr(self, '_face_proc') and self._face_proc and self._face_proc.poll() is None:
            try:
                with open('/tmp/face_auth_signal', 'w') as f:
                    f.write('quit')
                self._face_proc.wait(timeout=3)
            except Exception:
                self._face_proc.kill()
        elif hasattr(self, '_face_proc') and self._face_proc and self._face_proc.poll() is not None:
            try:
                self._face_proc.wait(timeout=1)
            except Exception:
                pass
        # 清理信号文件
        for f in ['/tmp/face_auth_signal', '/tmp/face_auth_result.json']:
            if os.path.exists(f):
                try: os.remove(f)
                except: pass
        # 启动新守护进程（守护进程内部会自己处理 camera 初始化和 fuser -k）
        try:
            self._face_proc = subprocess.Popen(
                [sys.executable, '/opt/smart-locker/scripts/face_auth_daemon.py'],
                cwd='/opt/smart-locker', env={**os.environ, 'DISPLAY': ':0'}
            )
            time.sleep(0.3)
        except Exception:
            self._face_proc = None
            print('[Qt] Face daemon failed to start')

    def _start_face_auth(self):
        if self._face_running:
            return
        self._face_running = True
        self._toast('正在启动人脸识别...', 0, icon='👤')
        QApplication.processEvents()
        QTimer.singleShot(200, self._face_auth_launch)

    def _face_auth_launch(self):
        self._face_result_file = '/tmp/face_auth_result.json'
        if os.path.exists(self._face_result_file):
            os.remove(self._face_result_file)
        self._face_start_time = time.time()

        if self._face_proc and self._face_proc.poll() is None:
            try:
                with open('/tmp/face_auth_signal', 'w') as f:
                    f.write(f'start:{self._face_result_file}')
            except Exception:
                pass
        else:
            try:
                self._face_proc = subprocess.Popen(
                    [sys.executable, '/opt/smart-locker/scripts/face_auth_gui.py',
                     '--output', self._face_result_file],
                    cwd='/opt/smart-locker', env={**os.environ, 'DISPLAY': ':0'}
                )
            except Exception:
                self._face_running = False
                self._toast('人脸识别启动失败')
                return

        if not hasattr(self, '_face_timer') or self._face_timer is None:
            self._face_timer = QTimer()
            self._face_timer.timeout.connect(self._check_face_result)
        self._face_timer.start(300)

    def _check_face_result(self):
        file_ready = os.path.exists(self._face_result_file)
        timed_out = time.time() - self._face_start_time > 20

        if file_ready or timed_out:
            self._face_timer.stop()
            self.overlay.hide()
            self._face_running = False
            if file_ready:
                try:
                    data = json.load(open(self._face_result_file, 'r'))
                    if data.get('ok') and data.get('user_id'):
                        user = self.db.get_user(data['user_id'])
                        if user:
                            self._on_login_success(user)
                            os.remove(self._face_result_file)
                            return
                except Exception:
                    pass
            if timed_out:
                self._toast('人脸识别超时，请重试')
                if self._face_proc and self._face_proc.poll() is None:
                    self._face_proc.kill()
            elif not file_ready:
                self._toast('人脸未匹配，请重试')

    def _on_login_success(self, user):
        self._logged_user = user
        self.login_user_input.clear()
        self.login_pwd_display.clear()
        self.nfc_timer.stop()
        self.overlay.hide()
        self._speak(f'{user["name"]}，验证成功')
        self._update_user_display()
        if self._return_context:
            self.go(self.PAGE_RETURN_MANUAL)
        else:
            self.go(self.PAGE_BORROW_METHOD)

    # ═══════════════════════════════════
    # PAGE 2: Borrow Method Selection
    # ═══════════════════════════════════
    def _init_borrow_method(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(40, 0, 40, 20)
        layout.addWidget(TitleBar('选择借出方式', back_cb=self.go_home))

        layout.addSpacing(30)

        lbl = QLabel('请选择借出方式')
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setStyleSheet(f"font-size:20px; color:{C_TX2};")
        layout.addWidget(lbl)
        layout.addSpacing(20)

        for text, icon, target in [
            ('按柜门选择', '📦', self.PAGE_BORROW_DIRECT),
            ('AI 智能推荐', '🤖', self.PAGE_BORROW_AI),
            ('按分类浏览', '📂', self.PAGE_BORROW_CATEGORY),
        ]:
            btn = QPushButton(f'{icon}  {text}')
            btn.setMinimumHeight(90)
            btn.setStyleSheet(f"""
                QPushButton {{ background:{C_BG3}; border:1px solid {C_BD};
                    border-radius:12px; font-size:20px; font-weight:bold; color:{C_TX}; }}
                QPushButton:hover {{ border-color:{C_BW}; }}
            """)
            btn.clicked.connect(lambda checked, t=target: self.go(t))
            layout.addWidget(btn)

        layout.addStretch()
        self.stack.addWidget(page)

    # ═══════════════════════════════════
    # PAGE 3: Borrow Direct (Cabinet Grid)
    # ═══════════════════════════════════
    CABINETS_PER_PAGE = 8

    def _init_borrow_direct(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(20, 0, 20, 15)
        layout.addWidget(TitleBar('按柜门借出', back_cb=lambda: self.go(self.PAGE_BORROW_METHOD)))

        self.cabinet_page_stack = QStackedWidget()
        layout.addWidget(self.cabinet_page_stack)

        nav = QHBoxLayout()
        self.cabinet_prev_btn = QPushButton('◀ 上一页')
        self.cabinet_prev_btn.setStyleSheet(
            f"QPushButton{{background:{C_BG3};color:{C_TX};font-size:15px;padding:10px;border-radius:8px;}}"
            f"QPushButton:disabled{{color:{C_TX2};}}")
        self.cabinet_prev_btn.clicked.connect(lambda: self.cabinet_page_stack.setCurrentIndex(
            max(0, self.cabinet_page_stack.currentIndex() - 1)))
        self.cabinet_page_label = QLabel()
        self.cabinet_page_label.setAlignment(Qt.AlignCenter)
        self.cabinet_page_label.setStyleSheet(f"font-size:14px;color:{C_TX2};")
        self.cabinet_next_btn = QPushButton('下一页 ▶')
        self.cabinet_next_btn.setStyleSheet(
            f"QPushButton{{background:{C_BG3};color:{C_TX};font-size:15px;padding:10px;border-radius:8px;}}"
            f"QPushButton:disabled{{color:{C_TX2};}}")
        self.cabinet_next_btn.clicked.connect(lambda: self.cabinet_page_stack.setCurrentIndex(
            min(self.cabinet_page_stack.count() - 1, self.cabinet_page_stack.currentIndex() + 1)))
        nav.addWidget(self.cabinet_prev_btn)
        nav.addWidget(self.cabinet_page_label)
        nav.addWidget(self.cabinet_next_btn)
        layout.addLayout(nav)

        self.cabinet_page_stack.currentChanged.connect(self._update_cabinet_nav)
        self.stack.addWidget(page)

    def _refresh_cabinet_grid(self):
        comps = self.db.get_all_components()
        cabinets = {}
        for c in comps:
            if c['cabinet_id'] not in cabinets:
                cabinets[c['cabinet_id']] = c
        cab_ids = sorted(cabinets.keys())
        pages = [cab_ids[i:i + self.CABINETS_PER_PAGE] for i in range(0, len(cab_ids), self.CABINETS_PER_PAGE)]

        while self.cabinet_page_stack.count() > 0:
            w = self.cabinet_page_stack.widget(0)
            self.cabinet_page_stack.removeWidget(w)
            w.deleteLater()

        for page_cabs in pages:
            grid_w = QWidget()
            grid = QGridLayout(grid_w)
            grid.setSpacing(10)
            row, col = 0, 0
            for cab_id in page_cabs:
                c = cabinets[cab_id]
                card = QPushButton()
                card.setMinimumHeight(110)
                card.setStyleSheet(f"""
                    QPushButton {{ background:{C_BG3}; border:1px solid {C_BD};
                        border-radius:10px; text-align:left; padding:12px; font-size:15px; color:{C_TX}; }}
                    QPushButton:hover {{ border-color:{C_BW}; }}
                """)
                card.setText(f"#{cab_id}号柜\n{c['name']}\n{c['category']} · 库存:{c['stock']}")
                card.clicked.connect(lambda checked, cid=cab_id, comp=c: self._borrow_confirm(comp))
                grid.addWidget(card, row, col)
                col += 1
                if col >= 2: col = 0; row += 1
            self.cabinet_page_stack.addWidget(grid_w)

        self.cabinet_page_stack.setCurrentIndex(0)
        self._update_cabinet_nav()

    def _update_cabinet_nav(self):
        total = self.cabinet_page_stack.count()
        if total <= 0:
            return
        cur = self.cabinet_page_stack.currentIndex()
        self.cabinet_prev_btn.setEnabled(cur > 0)
        self.cabinet_next_btn.setEnabled(cur < total - 1)
        self.cabinet_page_label.setText(f'第 {cur + 1}/{total} 页')
        vis = total > 1
        self.cabinet_prev_btn.setVisible(vis)
        self.cabinet_next_btn.setVisible(vis)
        self.cabinet_page_label.setVisible(vis)

    def _borrow_confirm(self, comp):
        if not self._logged_user:
            self._toast('请先登录'); return
        self._confirm_dialog(
            f'借出 {comp["name"]}',
            f'{comp["name"]}\n{comp["cabinet_id"]}号柜 · {comp["category"]}\n确定借出？',
            lambda: self._do_borrow(comp)
        )

    def _do_borrow(self, comp):
        cab = comp['cabinet_id']
        self._do_lock(cab)
        self._scan_context = 'borrow'
        self._borrow_comp = comp
        self._speak(f'{comp["name"]}，{cab}号柜已打开，请取出器件并扫码')
        self.go(self.PAGE_RETURN_SCAN)

    # ═══════════════════════════════════
    # PAGE 4: Borrow AI
    # ═══════════════════════════════════
    # Pinyin → Chinese terms dictionary (electronic components domain)
    PINYIN_DICT = [
        ('wenya', '稳压'), ('xinpian', '芯片'), ('wenya xinpian', '稳压芯片'),
        ('sanjiguan', '三极管'), ('npn', 'NPN三极管'), ('pnp', 'PNP三极管'),
        ('erjiguan', '二极管'), ('zhengliu', '整流'), ('zhengliu erjiguan', '整流二极管'),
        ('weikongzhiqi', '微控制器'), ('danpianji', '单片机'),
        ('wuxian', '无线'), ('mokuai', '模块'), ('wuxian mokuai', '无线模块'),
        ('wifi', 'WiFi'), ('lanya', '蓝牙'), ('wifi lanya', 'WiFi蓝牙'),
        ('jicheng', '集成'), ('dianlu', '电路'), ('jicheng dianlu', '集成电路'),
        ('yunfang', '运放'), ('dingshiqi', '定时器'), ('kaiguan', '开关'),
        ('fangda', '放大'), ('dianyuan', '电源'), ('chuanganqi', '传感器'),
        ('stm', 'STM32'), ('esp', 'ESP32'),
        ('ne', 'NE555'), ('lm', 'LM7805'), ('lm', 'LM358'),
        ('ams', 'AMS1117'), ('1n', '1N4007'), ('2n', '2N2222'),
    ]

    def _init_borrow_ai(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(20, 0, 20, 15)
        layout.addWidget(TitleBar('AI 智能推荐', back_cb=lambda: self.go(self.PAGE_BORROW_METHOD)))

        # Search bar
        search_row = QHBoxLayout()
        self.ai_search_display = QLineEdit()
        self.ai_search_display.setPlaceholderText('拼音输入搜索，如 wenya xinpian')
        self.ai_search_display.setFixedHeight(44)
        self.ai_search_display.setReadOnly(True)
        self.ai_search_display.setStyleSheet(f"background:{C_BG3}; font-size:15px;")
        search_row.addWidget(self.ai_search_display)

        search_btn = QPushButton('🔍')
        search_btn.setFixedSize(44, 44)
        search_btn.setStyleSheet(f"background:{C_JD}; color:#fff; font-size:18px; border-radius:8px;")
        search_btn.clicked.connect(lambda: self._ai_query_text(self.ai_search_display.text()))
        search_row.addWidget(search_btn)

        self.voice_btn = QPushButton('🎤')
        self.voice_btn.setFixedSize(44, 44)
        self.voice_btn.setStyleSheet(f"background:{C_AC}; color:#fff; font-size:18px; border-radius:8px;")
        self.voice_btn.clicked.connect(self._ai_voice_toggle)
        search_row.addWidget(self.voice_btn)

        clear_btn = QPushButton('✕')
        clear_btn.setFixedSize(44, 44)
        clear_btn.setStyleSheet(f"background:{C_BG3}; color:{C_TX2}; font-size:18px; border-radius:8px;")
        clear_btn.clicked.connect(lambda: (self.ai_search_display.clear(), self._clear_ai_candidates(), self._clear_pinyin_candidates()))
        search_row.addWidget(clear_btn)
        layout.addLayout(search_row)

        # Voice recording status bar (hidden by default)
        self.voice_record_bar = QWidget()
        vbar = QHBoxLayout(self.voice_record_bar)
        vbar.setContentsMargins(0, 4, 0, 0)
        self.voice_status_lbl = QLabel('')
        self.voice_status_lbl.setStyleSheet(f"font-size:14px; color:{C_AC}; font-weight:bold;")
        vbar.addWidget(self.voice_status_lbl)
        vbar.addStretch()
        self.voice_stop_btn = QPushButton('⏹ 停止录音')
        self.voice_stop_btn.setFixedHeight(36)
        self.voice_stop_btn.setStyleSheet(f"background:#d32f2f; color:#fff; font-size:14px; font-weight:bold; border-radius:8px;")
        self.voice_stop_btn.clicked.connect(self._ai_voice_toggle)
        vbar.addWidget(self.voice_stop_btn)
        self.voice_record_bar.setVisible(False)
        layout.addWidget(self.voice_record_bar)

        # Pinyin candidates bar
        self.pinyin_candidates = QHBoxLayout()
        layout.addLayout(self.pinyin_candidates)

        # AI result
        self.ai_result = QLabel('输入拼音搜索器件，或按 🎤 语音')
        self.ai_result.setAlignment(Qt.AlignCenter)
        self.ai_result.setStyleSheet(f"font-size:14px; color:{C_TX2}; padding:8px;")
        self.ai_result.setWordWrap(True)
        layout.addWidget(self.ai_result)

        self.ai_candidates = QVBoxLayout()
        layout.addLayout(self.ai_candidates)

        # QWERTY letter keyboard for pinyin
        self.ai_kb_stack = QStackedWidget()
        self.ai_kb_stack.setFixedHeight(170)
        lw = QWidget(); lg = QGridLayout(lw); lg.setSpacing(3)
        rows = ['QWERTYUIOP', 'ASDFGHJKL', 'ZXCVBNM']
        for r, keys in enumerate(rows):
            for c, ch in enumerate(keys):
                btn = QPushButton(ch)
                btn.setMinimumHeight(34)
                btn.setStyleSheet(f"background:{C_BG3}; font-size:14px; border-radius:4px;")
                btn.clicked.connect(lambda checked, ch=ch: self._on_ai_pinyin_letter(ch))
                lg.addWidget(btn, r, c)
        bk = QPushButton('⌫'); bk.setMinimumHeight(34)
        bk.setStyleSheet(f"background:{C_AC}; color:#fff; font-size:14px; border-radius:4px;")
        bk.clicked.connect(lambda: self._on_ai_pinyin_letter('BACK'))
        lg.addWidget(bk, 2, 8)
        sp = QPushButton('空格'); sp.setMinimumHeight(34)
        sp.setStyleSheet(f"background:{C_BG3}; font-size:13px; border-radius:4px;")
        sp.clicked.connect(lambda: self._on_ai_pinyin_letter(' '))
        lg.addWidget(sp, 3, 0, 1, 10)
        self.ai_kb_stack.addWidget(lw)
        layout.addWidget(self.ai_kb_stack)

        self.stack.addWidget(page)

    def _on_ai_pinyin_letter(self, ch):
        cur = self.ai_search_display.text()
        if ch == 'BACK':
            cur = cur[:-1]
        else:
            cur += ch
        self.ai_search_display.setText(cur)
        self._match_pinyin(cur)

    def _match_pinyin(self, text):
        self._clear_pinyin_candidates()
        text = text.lower().strip()
        if not text: return
        parts = text.split()
        last = parts[-1] if parts else text
        # Find matches where pinyin starts with the last word
        matches = []
        for py, cn in self.PINYIN_DICT:
            if py.startswith(last):
                # Score: exact match first, then prefix match
                score = 0 if py == last else len(last)
                matches.append((score, cn))
            elif ' ' in py:
                # Check if last word matches any word in compound pinyin
                for pw in py.split():
                    if pw.startswith(last):
                        matches.append((len(last) + 1, cn))
                        break
        matches.sort(key=lambda x: x[0])
        seen = set()
        for _, cn in matches:
            if cn not in seen:
                seen.add(cn)
                btn = QPushButton(cn)
                btn.setMinimumHeight(34)
                btn.setStyleSheet(f"background:{C_BW}; color:#fff; font-size:14px; border-radius:6px; padding:4px 10px;")
                btn.clicked.connect(lambda checked, c=cn: self._commit_pinyin(c))
                self.pinyin_candidates.addWidget(btn)

    def _commit_pinyin(self, cn_word):
        cur = self.ai_search_display.text().strip()
        # Replace last pinyin word with Chinese
        parts = cur.rsplit(' ', 1)
        # Keep previous committed Chinese + new word
        prefix = ''
        for i, part in enumerate(parts):
            # Check if this part is already Chinese (contains non-ASCII) or English word
            if any(ord(c) > 127 for c in part):
                prefix += part
            else:
                # It's pinyin, try to convert
                pass
        # Simple: append the Chinese word
        new_text = cur + ' ' + cn_word if cur else cn_word
        # Better: replace last pinyin word
        if parts:
            last_is_pinyin = all(ord(c) < 128 for c in parts[-1])
            if last_is_pinyin:
                new_text = (' '.join(parts[:-1]) + ' ' + cn_word).strip()
            else:
                new_text = cur + cn_word
        self.ai_search_display.setText(new_text)
        self._match_pinyin('')

    def _clear_pinyin_candidates(self):
        for i in reversed(range(self.pinyin_candidates.count())):
            w = self.pinyin_candidates.itemAt(i).widget()
            if w: w.deleteLater()

    def _build_catalog(self):
        lines = []
        seen = set()
        for c in self.db.get_all_components():
            cid = c.get('cabinet_id', 0)
            if cid in seen: continue
            if c.get('stock', 0) <= 0: continue
            seen.add(cid)
            vid = f"{c.get('voltage', 0) or 0:.1f}V"
            kw = c.get('keywords', '').replace(',', ' ')
            # Enrich name with category + keywords so AI rule matching finds them
            name = f"{c['name']} {c.get('category','')} {kw}"
            lines.append(f"{c['id']}. {name} | {c.get('category','')} | {vid} | 柜门{cid}")
        return '\n'.join(lines)

    def _init_llm(self):
        if self.ai_engine._llm_available:
            return True
        self._toast('正在加载 AI 模型...（约5秒）', 0)
        QApplication.processEvents()
        try:
            self.ai_engine.initialize()
            print('[Qt] LLM model loaded OK')
            self._toast('AI 模型就绪', 1500)
            return True
        except Exception as e:
            print(f'[Qt] LLM load failed: {e}')
            self._toast('AI 模型加载失败')
            return False

    def _ai_query_text(self, text):
        text = text.strip()
        if not text: return
        self._clear_ai_candidates()
        if not self.ai_engine:
            self.ai_result.setText('AI 服务未就绪')
            return

        # Step 1: Fast rule matching (instant)
        self.ai_engine.set_catalog(self._build_catalog())
        result = self.ai_engine.process_query(text)

        matched_comp = None
        if result.component_id:
            matched_comp = self.db.get_component(result.component_id)
        elif result.is_ambiguous and result.candidates:
            # Show candidates from rule matching
            self.ai_result.setText(result.response_text)
            for i, cand in enumerate(result.candidates[:5]):
                c = self.db.get_component(cand.component_id) if cand.component_id else None
                if c:
                    row = QPushButton(f"{i+1}. {c['name']} ({c['cabinet_id']}号柜) — {cand.category}")
                    row.setFixedHeight(40)
                    row.setStyleSheet(f"background:{C_BG3}; font-size:14px;")
                    row.clicked.connect(lambda checked, comp=c: (self._borrow_confirm(comp), self._clear_ai_candidates()))
                    self.ai_candidates.addWidget(row)
            self._speak('库存有多款匹配器件，请在屏幕上选择')

        if matched_comp:
            conf = int(result.confidence * 100) if result.confidence else 0
            self.ai_result.setText(
                f'匹配: {matched_comp["name"]}\n'
                f'{matched_comp["cabinet_id"]}号柜 · {matched_comp.get("category","")}\n'
                f'库存: {matched_comp.get("stock",0)} · 置信度: {conf}%'
            )
            self._speak(f'为您找到{matched_comp["name"]}，{matched_comp["cabinet_id"]}号柜')
            confirm = QPushButton(f'确认借出 {matched_comp["name"]}')
            confirm.setFixedHeight(56)
            confirm.setStyleSheet(f"background:{C_JD}; color:#fff; font-size:18px; border-radius:10px;")
            confirm.clicked.connect(lambda checked, c=matched_comp: (self._borrow_confirm(c), self._clear_ai_candidates()))
            self.ai_candidates.addWidget(confirm)

        # Show "Deep AI" button for LLM analysis
        deep_btn = QPushButton('🤖 AI 深度分析')
        deep_btn.setFixedHeight(38)
        deep_btn.setStyleSheet(f"background:{C_BW}; color:#fff; font-size:14px; border-radius:8px;")
        deep_btn.clicked.connect(lambda: self._ai_deep_analyze(text))
        self.ai_candidates.addWidget(deep_btn)

    def _ai_deep_analyze(self, text):
        if not self._init_llm():
            return
        self._clear_ai_candidates()
        self._toast('AI 正在分析...（约20秒）', 0)
        QApplication.processEvents()

        # Build inventory
        items = []
        seen = set()
        for c in self.db.get_all_components():
            cid = c.get('cabinet_id', 0)
            if cid in seen: continue
            if c.get('stock', 0) <= 0: continue
            seen.add(cid)
            vid = f"{c.get('voltage', 0) or 0:.1f}V"
            aid = f"{c.get('current', 0) or 0:.2f}A"
            kw = c.get('keywords', '')
            items.append(
                f"ID:{c['id']} | {c['name']} | {c.get('category','')} | {vid} {aid}"
                f" | 柜门{cid} | 库存{c.get('stock',0)}"
                + (f" | {kw}" if kw else "")
            )

        try:
            response = self._llm_recommend(text, items)
            cid = int(response.get('component_id', 0)) if response else 0
            if cid > 0:
                comp = self.db.get_component(cid)
                if comp:
                    name = response.get('name', comp['name'])
                    chars = response.get('characteristics', '')
                    reason = response.get('match_reason', '')
                    alts = response.get('alternatives', '')
                    lines = [
                        f'🤖 AI 推荐：{name}',
                        f'{comp["cabinet_id"]}号柜 · {comp.get("category","")} · 库存{comp.get("stock",0)}',
                        '',
                    ]
                    if chars:
                        lines.append(f'📋 器件特性：{chars}')
                        lines.append('')
                    if reason:
                        lines.append(f'🎯 匹配分析：{reason}')
                        lines.append('')
                    if alts:
                        lines.append(f'🔄 备选对比：{alts}')
                    self.ai_result.setText('\n'.join(lines))
                    self._speak(f'AI推荐{name}，{reason}')
                    confirm = QPushButton(f'确认借出 {comp["name"]}')
                    confirm.setFixedHeight(56)
                    confirm.setStyleSheet(f"background:{C_JD}; color:#fff; font-size:18px; border-radius:10px;")
                    confirm.clicked.connect(lambda checked, c=comp: (
                        self._borrow_confirm(c), self._clear_ai_candidates()))
                    self.ai_candidates.addWidget(confirm)
                    return
            self.ai_result.setText('AI 深度分析未能匹配到合适器件\n请换个方式描述或使用分类借出')
        except Exception as e:
            print(f'[Qt] LLM failed: {e}')
            self.ai_result.setText('AI 模型推理失败，请使用规则匹配结果')

    def _llm_recommend(self, query, items):
        prompt = f"""你是电子元器件专家。根据库存为用户推荐最合适的器件。

库存列表（每行一个器件）：
{chr(10).join(items)}

用户需求：{query}

请分析需求并推荐最佳器件。回复以下JSON格式（不要其他内容）：
{{"component_id":数字,"name":"器件名","characteristics":"器件特性和参数介绍（80字以内）","match_reason":"为什么这个器件适合用户的需求（80字以内）","alternatives":"其他备选器件及简要对比（60字以内）"}}"""

        response = self.ai_engine._rkllm.generate(prompt)
        import re
        m = re.search(r'```(?:json)?\s*(\{[^`]+\})\s*```', response, re.DOTALL)
        if not m:
            m = re.search(r'\{[^{}]*"component_id"[^{}]*\}', response)
        if m:
            raw = m.group(1) if m.lastindex else m.group(0)
            try:
                data = json.loads(raw)
                if 'component_id' in data:
                    data['component_id'] = int(data['component_id'])
                return data
            except (json.JSONDecodeError, ValueError, TypeError):
                return None
        return None

    def _clear_ai_candidates(self):
        for i in reversed(range(self.ai_candidates.count())):
            w = self.ai_candidates.itemAt(i).widget()
            if w: w.deleteLater()

    MAX_RECORD_SECONDS = 30
    PARTIAL_POLL_MS = 250

    def _ai_voice_toggle(self):
        """Toggle voice recording: tap to start, tap again to stop."""
        if not self._vosk_model:
            self._toast('语音模型未加载，请使用键盘输入', 2500)
            return
        if self._recording:
            self._stop_recording()
        else:
            self._start_recording()

    def _start_recording(self):
        """Start arecord via pipe → Vosk streaming with real-time partial display."""
        import threading
        from vosk import KaldiRecognizer

        self._recording = True
        self._record_seconds = 0
        self._record_text_final = None  # Set when final result arrives
        self._record_text_partial = ''

        # Per-session Vosk recognizer
        self._record_recognizer = KaldiRecognizer(self._vosk_model, 16000)
        self._record_recognizer.SetMaxAlternatives(0)

        # UI: recording state
        self.voice_btn.setText('⏹')
        self.voice_btn.setStyleSheet(f"background:#d32f2f; color:#fff; font-size:18px; border-radius:8px;")
        self.voice_status_lbl.setText('🔴 正在录音... 0 / 30 秒')
        self.voice_record_bar.setVisible(True)
        self.ai_result.setText('🎤 正在聆听...')

        # Launch arecord with stdout pipe (plughw handles 48k→16k resampling)
        try:
            self._record_proc = subprocess.Popen(
                ['arecord', '-D', 'plughw:3,0', '-f', 'S16_LE', '-r', '16000', '-c', '1', '-'],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        except Exception:
            self._stop_recording()
            self._toast('麦克风启动失败', 2000)
            return

        # Reader thread: feed Vosk from pipe with audio gain normalization
        self._record_reader_done = False
        def reader():
            try:
                import numpy as np
                while self._recording and self._record_proc and self._record_proc.stdout:
                    data = self._record_proc.stdout.read(4000)
                    if not data:
                        break
                    # Audio gain normalization (same as voice_recognizer.py):
                    # amplify quiet signals so Vosk can detect speech at normal volumes
                    mono = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0
                    rms = float(np.sqrt(np.mean(mono ** 2)))
                    if 1e-6 < rms < 0.02:
                        mono = mono * (0.08 / rms)
                    data = (mono * 32767).clip(-32768, 32767).astype(np.int16).tobytes()
                    if self._record_recognizer:
                        self._record_recognizer.AcceptWaveform(data)
            except Exception as e:
                print(f'[Qt] Voice reader error: {e}')
                import traceback
                traceback.print_exc()
            finally:
                self._record_reader_done = True

        self._record_reader_thread = threading.Thread(target=reader, daemon=True)
        self._record_reader_thread.start()

        # Partial poll timer — update display with interim recognition
        self._record_partial_timer = QTimer()
        self._record_partial_timer.timeout.connect(self._on_partial_poll)
        self._record_partial_timer.start(self.PARTIAL_POLL_MS)

        # Countdown timer — update every second
        self._record_countdown = QTimer()
        self._record_countdown.timeout.connect(self._on_record_tick)
        self._record_countdown.start(1000)

        # Auto-stop timer — 30s max
        self._record_timer = QTimer()
        self._record_timer.setSingleShot(True)
        self._record_timer.timeout.connect(self._stop_recording)
        self._record_timer.start(self.MAX_RECORD_SECONDS * 1000)

    def _on_partial_poll(self):
        """Poll Vosk partial recognition and update display in real-time."""
        if not self._recording or not hasattr(self, '_record_recognizer') or not self._record_recognizer:
            return
        try:
            import json as _json
            partial = _json.loads(self._record_recognizer.PartialResult())
            text = partial.get('partial', '').strip()
            if text and text != self._record_text_partial:
                self._record_text_partial = text
                self.ai_result.setText(f'🎤 识别中: {text}')
        except Exception:
            pass

    def _on_record_tick(self):
        self._record_seconds += 1
        partial_hint = ''
        if hasattr(self, '_record_text_partial') and self._record_text_partial:
            partial_hint = '  |  ' + self._record_text_partial[:30]
        self.voice_status_lbl.setText(f'🔴 录音 {self._record_seconds}/{self.MAX_RECORD_SECONDS} 秒{partial_hint}')

    def _stop_recording(self):
        """Stop recording, get final Vosk result, submit to AI search."""
        # Stop timers
        for t in ['_record_timer', '_record_countdown', '_record_partial_timer']:
            timer = getattr(self, t, None)
            if timer:
                timer.stop()
                setattr(self, t, None)

        self._recording = False

        # Kill arecord subprocess
        if self._record_proc:
            try:
                self._record_proc.terminate()
                self._record_proc.wait(timeout=2)
            except Exception:
                try: self._record_proc.kill()
                except: pass
            self._record_proc = None

        # Reset UI
        self.voice_btn.setText('🎤')
        self.voice_btn.setStyleSheet(f"background:{C_AC}; color:#fff; font-size:18px; border-radius:8px;")
        self.voice_record_bar.setVisible(False)

        # Wait for reader thread to finish processing last audio chunk
        if hasattr(self, '_record_reader_thread') and self._record_reader_thread:
            self._record_reader_thread.join(timeout=1.5)

        # Get final recognition result
        text = ''
        try:
            import json as _json
            if hasattr(self, '_record_recognizer') and self._record_recognizer:
                final = _json.loads(self._record_recognizer.FinalResult())
                text = final.get('text', '').strip()
                # Diagnostic: if empty, log partial to understand why
                if not text:
                    partial_raw = self._record_recognizer.PartialResult()
                    partial = _json.loads(partial_raw).get('partial', '')
                    print(f'[Qt] Voice empty final, partial was: "{partial}"')
        except Exception as e:
            print(f'[Qt] Voice final error: {e}')

        self._record_recognizer = None

        if text:
            self._toast(f'识别: {text}', 2000)
            self._ai_query_text(text)
        else:
            self._toast('未识别到语音，请重试', 2500)
            self.ai_result.setText('输入拼音搜索器件，或按 🎤 语音')

    # ═══════════════════════════════════
    # PAGE 5: Borrow Category List
    # ═══════════════════════════════════
    def _init_borrow_category(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(40, 0, 40, 20)
        layout.addWidget(TitleBar('按分类借出', back_cb=lambda: self.go(self.PAGE_BORROW_METHOD)))

        layout.addSpacing(20)
        categories = ['稳压芯片', '三极管', '微控制器', '无线模块', '二极管', '集成电路']
        for cat in categories:
            btn = QPushButton(cat)
            btn.setMinimumHeight(55)
            btn.setStyleSheet(f"""
                QPushButton {{ background:{C_BG3}; border:1px solid {C_BD};
                    border-radius:10px; font-size:18px; }}
                QPushButton:hover {{ border-color:{C_BW}; }}
            """)
            btn.clicked.connect(lambda checked, c=cat: self._show_category(c))
            layout.addWidget(btn)

        layout.addStretch()
        self.stack.addWidget(page)

    def _show_category(self, cat):
        self._selected_category = cat
        self.go(self.PAGE_CATEGORY_DETAIL)

    # ═══════════════════════════════════
    # PAGE 6: Category Detail (new page)
    # ═══════════════════════════════════
    def _init_category_detail(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(20, 0, 20, 15)
        layout.addWidget(TitleBar('分类详情', back_cb=lambda: self.go(self.PAGE_BORROW_CATEGORY)))

        self.cat_title = QLabel()
        self.cat_title.setAlignment(Qt.AlignCenter)
        self.cat_title.setStyleSheet(f"font-size:22px; font-weight:bold; color:{C_TX}; padding:10px;")
        layout.addWidget(self.cat_title)

        self.cat_detail_pages = QStackedWidget()
        layout.addWidget(self.cat_detail_pages)

        nav = QHBoxLayout()
        self.cat_prev_btn = QPushButton('◀ 上一页')
        self.cat_prev_btn.setStyleSheet(
            f"QPushButton{{background:{C_BG3};color:{C_TX};font-size:15px;padding:10px;border-radius:8px;}}"
            f"QPushButton:disabled{{color:{C_TX2};}}")
        self.cat_prev_btn.clicked.connect(lambda: self.cat_detail_pages.setCurrentIndex(
            max(0, self.cat_detail_pages.currentIndex() - 1)))
        self.cat_page_label = QLabel()
        self.cat_page_label.setAlignment(Qt.AlignCenter)
        self.cat_page_label.setStyleSheet(f"font-size:14px;color:{C_TX2};")
        self.cat_next_btn = QPushButton('下一页 ▶')
        self.cat_next_btn.setStyleSheet(
            f"QPushButton{{background:{C_BG3};color:{C_TX};font-size:15px;padding:10px;border-radius:8px;}}"
            f"QPushButton:disabled{{color:{C_TX2};}}")
        self.cat_next_btn.clicked.connect(lambda: self.cat_detail_pages.setCurrentIndex(
            min(self.cat_detail_pages.count() - 1, self.cat_detail_pages.currentIndex() + 1)))
        nav.addWidget(self.cat_prev_btn)
        nav.addWidget(self.cat_page_label)
        nav.addWidget(self.cat_next_btn)
        layout.addLayout(nav)
        self.cat_detail_pages.currentChanged.connect(self._update_cat_nav)
        self.stack.addWidget(page)

    CAT_ITEMS_PER_PAGE = 6

    def _refresh_category_detail(self):
        if not self._selected_category: return
        self.cat_title.setText(self._selected_category)

        comps = self.db.search_components(keyword='', category=self._selected_category)
        pages = [comps[i:i + self.CAT_ITEMS_PER_PAGE] for i in range(0, len(comps), self.CAT_ITEMS_PER_PAGE)]

        while self.cat_detail_pages.count() > 0:
            w = self.cat_detail_pages.widget(0)
            self.cat_detail_pages.removeWidget(w)
            w.deleteLater()

        if not comps:
            empty_w = QWidget()
            el = QVBoxLayout(empty_w)
            lbl = QLabel('该分类暂无器件')
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setStyleSheet(f"font-size:16px; color:{C_TX2};")
            el.addWidget(lbl)
            self.cat_detail_pages.addWidget(empty_w)
        else:
            for page_comps in pages:
                pw = QWidget()
                pl = QVBoxLayout(pw)
                for c in page_comps:
                    row = QWidget()
                    row.setStyleSheet(f"background:{C_BG3}; border-radius:8px; padding:8px; margin:4px;")
                    rl = QHBoxLayout(row)
                    info = QLabel(f"{c['name']}\n{c['cabinet_id']}号柜 · 库存:{c['stock']}")
                    info.setStyleSheet(f"font-size:14px; color:{C_TX};")
                    rl.addWidget(info, 1)
                    btn = QPushButton('借出')
                    btn.setFixedSize(130, 62)
                    btn.setStyleSheet(f"background:{C_JD}; color:#fff; font-size:18px; border-radius:10px;")
                    btn.clicked.connect(lambda checked, comp=c: self._borrow_confirm(comp))
                    rl.addWidget(btn)
                    pl.addWidget(row)
                self.cat_detail_pages.addWidget(pw)

        self.cat_detail_pages.setCurrentIndex(0)
        self._update_cat_nav()

    def _update_cat_nav(self):
        total = self.cat_detail_pages.count()
        if total <= 0: return
        cur = self.cat_detail_pages.currentIndex()
        self.cat_prev_btn.setEnabled(cur > 0)
        self.cat_next_btn.setEnabled(cur < total - 1)
        self.cat_page_label.setText(f'第 {cur + 1}/{total} 页')
        vis = total > 1
        self.cat_prev_btn.setVisible(vis)
        self.cat_next_btn.setVisible(vis)
        self.cat_page_label.setVisible(vis)

    # ═══════════════════════════════════
    # PAGE 7: Return Method Selection
    # ═══════════════════════════════════
    def _init_return_method(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(40, 0, 40, 20)
        layout.addWidget(TitleBar('归还器件', back_cb=self.go_home))

        layout.addSpacing(30)
        lbl = QLabel('请选择归还方式')
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setStyleSheet(f"font-size:20px; color:{C_TX2};")
        layout.addWidget(lbl)
        layout.addSpacing(20)

        for text, icon, target in [
            ('扫码归还', '📷', self.PAGE_RETURN_SCAN),
            ('手动归还', '👤', self.PAGE_RETURN_MANUAL),
        ]:
            btn = QPushButton(f'{icon}  {text}')
            btn.setMinimumHeight(100)
            btn.setStyleSheet(f"""
                QPushButton {{ background:{C_BG3}; border:1px solid {C_BD};
                    border-radius:12px; font-size:20px; font-weight:bold; color:{C_TX}; }}
                QPushButton:hover {{ border-color:{C_BW}; }}
            """)
            btn.clicked.connect(lambda checked, t=target: self._start_return_flow(t))
            layout.addWidget(btn)

        layout.addStretch()
        self.stack.addWidget(page)

    def _start_return_flow(self, target):
        if target == self.PAGE_RETURN_MANUAL:
            self._return_context = True
            self.go(self.PAGE_LOGIN)
        else:
            self.go(self.PAGE_RETURN_SCAN)

    # ═══════════════════════════════════
    # PAGE 8: Return Manual
    # ═══════════════════════════════════
    def _init_return_manual(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(20, 0, 20, 15)
        layout.addWidget(TitleBar('手动归还', back_cb=self.go_home))

        self.return_list_pages = QStackedWidget()
        layout.addWidget(self.return_list_pages)

        nav = QHBoxLayout()
        self.ret_prev_btn = QPushButton('◀ 上一页')
        self.ret_prev_btn.setStyleSheet(
            f"QPushButton{{background:{C_BG3};color:{C_TX};font-size:15px;padding:10px;border-radius:8px;}}"
            f"QPushButton:disabled{{color:{C_TX2};}}")
        self.ret_prev_btn.clicked.connect(lambda: self.return_list_pages.setCurrentIndex(
            max(0, self.return_list_pages.currentIndex() - 1)))
        self.ret_page_label = QLabel()
        self.ret_page_label.setAlignment(Qt.AlignCenter)
        self.ret_page_label.setStyleSheet(f"font-size:14px;color:{C_TX2};")
        self.ret_next_btn = QPushButton('下一页 ▶')
        self.ret_next_btn.setStyleSheet(
            f"QPushButton{{background:{C_BG3};color:{C_TX};font-size:15px;padding:10px;border-radius:8px;}}"
            f"QPushButton:disabled{{color:{C_TX2};}}")
        self.ret_next_btn.clicked.connect(lambda: self.return_list_pages.setCurrentIndex(
            min(self.return_list_pages.count() - 1, self.return_list_pages.currentIndex() + 1)))
        nav.addWidget(self.ret_prev_btn)
        nav.addWidget(self.ret_page_label)
        nav.addWidget(self.ret_next_btn)
        layout.addLayout(nav)
        self.return_list_pages.currentChanged.connect(self._update_ret_nav)
        self.stack.addWidget(page)

    RET_ITEMS_PER_PAGE = 6

    def _refresh_return_list(self):
        if not self._logged_user:
            while self.return_list_pages.count() > 0:
                w = self.return_list_pages.widget(0)
                self.return_list_pages.removeWidget(w)
                w.deleteLater()
            empty_w = QWidget()
            el = QVBoxLayout(empty_w)
            lbl = QLabel('请先登录'); lbl.setAlignment(Qt.AlignCenter)
            el.addWidget(lbl)
            self.return_list_pages.addWidget(empty_w)
            self.return_list_pages.setCurrentIndex(0)
            self._update_ret_nav()
            return

        records = self.db.get_user_records(self._logged_user['id'])
        borrowed = [r for r in records if r['status'] == 'borrowed']

        while self.return_list_pages.count() > 0:
            w = self.return_list_pages.widget(0)
            self.return_list_pages.removeWidget(w)
            w.deleteLater()

        if not borrowed:
            empty_w = QWidget()
            el = QVBoxLayout(empty_w)
            lbl = QLabel('没有待归还的器件')
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setStyleSheet(f"font-size:16px; color:{C_TX2};")
            el.addWidget(lbl)
            self.return_list_pages.addWidget(empty_w)
        else:
            items = [({'type': 'header', 'name': self._logged_user['name']})] + \
                    [{'type': 'record', 'data': r} for r in borrowed]
            pages = [items[i:i + self.RET_ITEMS_PER_PAGE] for i in range(0, len(items), self.RET_ITEMS_PER_PAGE)]
            for page_items in pages:
                pw = QWidget()
                pl = QVBoxLayout(pw)
                for item in page_items:
                    if item['type'] == 'header':
                        user_lbl = QLabel(f'用户: {item["name"]}')
                        user_lbl.setStyleSheet(f"font-size:16px; font-weight:bold; color:{C_TX}; padding:8px;")
                        pl.addWidget(user_lbl)
                    else:
                        r = item['data']
                        comp = self.db.get_component(r['component_id'])
                        name = comp['name'] if comp else '未知'
                        cab = r.get('cabinet_id', comp.get('cabinet_id', 0) if comp else 0)
                        row = QWidget()
                        row.setStyleSheet(f"background:{C_BG3}; border-radius:8px; padding:8px; margin:4px;")
                        rl = QHBoxLayout(row)
                        info = QLabel(f"{name}  |  {cab}号柜  |  {r['borrow_time']}")
                        info.setStyleSheet(f"font-size:14px;")
                        rl.addWidget(info, 1)
                        btn = QPushButton('归还')
                        btn.setFixedSize(130, 62)
                        btn.setStyleSheet(f"background:{C_JD}; color:#fff; font-size:18px; border-radius:10px;")
                        btn.clicked.connect(lambda checked, rid=r['id'], cabid=cab, n=name:
                            self._confirm_dialog(f'归还 {n}', f'确认归还 {n}？',
                                lambda rid=rid, cabid=cabid, n=n: self._do_return(rid, cabid, n)))
                        rl.addWidget(btn)
                        pl.addWidget(row)
                self.return_list_pages.addWidget(pw)

        self.return_list_pages.setCurrentIndex(0)
        self._update_ret_nav()

    def _update_ret_nav(self):
        total = self.return_list_pages.count()
        if total <= 0: return
        cur = self.return_list_pages.currentIndex()
        self.ret_prev_btn.setEnabled(cur > 0)
        self.ret_next_btn.setEnabled(cur < total - 1)
        self.ret_page_label.setText(f'第 {cur + 1}/{total} 页')
        vis = total > 1
        self.ret_prev_btn.setVisible(vis)
        self.ret_next_btn.setVisible(vis)
        self.ret_page_label.setVisible(vis)

    def _do_return(self, record_id, cabinet, name):
        rec = self.db.get_record(record_id)
        self.db.complete_return(record_id)
        if rec and rec.get('component_id'):
            self.db.conn.execute('UPDATE components SET stock = stock + 1 WHERE id = ?', (rec['component_id'],))
            self.db.conn.commit()
        # Also update inventory_items if this record is tied to an item
        self.db.conn.execute(
            "UPDATE inventory_items SET status='in_stock', record_id=NULL WHERE record_id=? AND status='borrowed'",
            (record_id,))
        self.db.conn.commit()
        self._do_lock(cabinet)
        self._speak(f'{name} 归还成功')
        self._toast(f'{name} 归还成功')
        self._refresh_return_list()

    # ═══════════════════════════════════
    # PAGE 9: Return Scan
    # ═══════════════════════════════════
    def _scan_back(self):
        """Context-aware back from scan page"""
        if hasattr(self, '_scan_context') and self._scan_context == 'borrow':
            self._scan_context = None
            self._borrow_comp = None
            if hasattr(self, 'scan_timer') and self.scan_timer.isActive():
                self.scan_timer.stop()
            self.go(self.PAGE_BORROW_DIRECT)
        else:
            self.go_home()

    def _init_return_scan(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(20, 0, 20, 15)
        layout.addWidget(TitleBar('扫码', back_cb=self._scan_back))

        self.scan_status = QLabel('等待扫码...')
        self.scan_status.setAlignment(Qt.AlignCenter)
        self.scan_status.setStyleSheet(f"font-size:22px; color:{C_TX2}; padding:40px;")
        layout.addWidget(self.scan_status)

        self.scan_detail = QLabel('将条码对准扫码器')
        self.scan_detail.setAlignment(Qt.AlignCenter)
        self.scan_detail.setStyleSheet(f"font-size:14px; color:{C_TX3};")
        layout.addWidget(self.scan_detail)
        layout.addStretch()

        cancel_btn = QPushButton('取消扫码')
        cancel_btn.setFixedHeight(50)
        cancel_btn.setStyleSheet(f"background:{C_AC}; color:#fff; font-size:16px; border-radius:8px;")
        cancel_btn.clicked.connect(self._scan_back)
        layout.addWidget(cancel_btn)

        self.scan_timer = QTimer()
        self.scan_timer.timeout.connect(self._poll_barcode)
        self._barcode_scanner = None

        self.stack.addWidget(page)

    def _poll_barcode(self):
        if not self._barcode_scanner:
            try:
                from src.auth.barcode_scanner import BarcodeScanner
                self._barcode_scanner = BarcodeScanner()
                self._barcode_scanner.initialize()
            except Exception:
                self.scan_timer.stop()
                self.scan_status.setText('扫码器未就绪')
                return
        try:
            barcode = self._barcode_scanner.scan_once(timeout=0.5)
            if barcode:
                self._on_barcode(barcode)
        except Exception:
            pass

    def _on_barcode(self, barcode):
        # Borrow mode: confirm which specific item was taken from cabinet
        if hasattr(self, '_scan_context') and self._scan_context == 'borrow' and hasattr(self, '_borrow_comp'):
            item = self.db.get_item_by_barcode(barcode)
            comp = self._borrow_comp
            if not item:
                self.scan_status.setText(f'条码未绑定: {barcode}'); return
            if item['component_id'] != comp['id']:
                self.scan_status.setText(f'条码不匹配，需要 {comp["name"]}'); return
            if item['status'] != 'in_stock':
                self.scan_status.setText(f'{comp["name"]} 已被借出'); return
            rec_id = self.db.create_borrow_record(
                self._logged_user['id'], item['component_id'], comp['cabinet_id'], 'direct')
            self.db.mark_item_borrowed(item['id'], rec_id)
            self._speak(f'{comp["name"]} 借出成功')
            self._toast(f'借出成功！{comp["name"]}')
            self.scan_status.setText(f'{comp["name"]} ✓ 借出成功')
            self.scan_detail.setText(f'{comp["cabinet_id"]}号柜')
            if hasattr(self, 'scan_timer') and self.scan_timer.isActive():
                self.scan_timer.stop()
            self._refresh_cabinet_grid()
            self._scan_context = None
            self._borrow_comp = None
            return

        # Return mode
        item = self.db.get_item_by_barcode(barcode)
        if not item:
            self.scan_status.setText('未注册条码'); return
        if item['status'] != 'borrowed':
            self.scan_status.setText(f'{item["component_name"]} 未借出'); return
        result = self.db.mark_item_returned(barcode)
        if not result:
            self.scan_status.setText('归还失败'); return
        if result.get('record_id'):
            self.db.complete_return(result['record_id'])
        cab = result.get('cabinet_id', 0)
        self.scan_status.setText(f'{result["name"]} 归还中...')
        self._do_lock(cab)
        self._speak(f'{result["name"]} 归还成功')
        self.scan_status.setText(f'{result["name"]} ✓ 归还成功')
        self.scan_detail.setText(f'{cab}号柜已打开')

    # ═══════════════════════════════════
    # PAGE 10: Register
    # ═══════════════════════════════════
    def _init_register(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(40, 0, 40, 20)
        layout.addWidget(TitleBar('用户注册', back_cb=self.go_home))
        layout.addSpacing(20)

        self.reg_name = QLineEdit(); self.reg_name.setPlaceholderText('用户名'); self.reg_name.setReadOnly(True); self.reg_name.setFixedHeight(45)
        layout.addWidget(self.reg_name)
        self.reg_pwd = QLineEdit(); self.reg_pwd.setPlaceholderText('密码'); self.reg_pwd.setEchoMode(QLineEdit.Password); self.reg_pwd.setReadOnly(True); self.reg_pwd.setFixedHeight(45)
        layout.addWidget(self.reg_pwd)
        self.reg_pwd2 = QLineEdit(); self.reg_pwd2.setPlaceholderText('确认密码'); self.reg_pwd2.setEchoMode(QLineEdit.Password); self.reg_pwd2.setReadOnly(True); self.reg_pwd2.setFixedHeight(45)
        layout.addWidget(self.reg_pwd2)

        # 键盘区域：字母键盘 / 数字键盘 切换
        self.reg_kb_stack = QStackedWidget()
        self.reg_kb_stack.setFixedHeight(200)

        # QWERTY 字母键盘
        letter_w = QWidget()
        letter_grid = QGridLayout(letter_w); letter_grid.setSpacing(4)
        qwerty = ['QWERTYUIOP', 'ASDFGHJKL', 'ZXCVBNM']
        for r, keys in enumerate(qwerty):
            for c, ch in enumerate(keys):
                btn = QPushButton(ch)
                btn.setMinimumHeight(36)
                btn.setStyleSheet(f"background:{C_BG3}; font-size:15px; border-radius:4px;")
                btn.clicked.connect(lambda checked, ch=ch: self._on_reg_letter(ch))
                letter_grid.addWidget(btn, r, c)
        back_btn = QPushButton('⌫')
        back_btn.setMinimumHeight(36)
        back_btn.setStyleSheet(f"background:{C_AC}; color:#fff; font-size:14px; border-radius:4px;")
        back_btn.clicked.connect(lambda: self._on_reg_letter('BACK'))
        letter_grid.addWidget(back_btn, 2, 8, 1, 2)
        space_btn = QPushButton('空格')
        space_btn.setMinimumHeight(36)
        space_btn.setStyleSheet(f"background:{C_BG3}; font-size:14px; border-radius:4px;")
        space_btn.clicked.connect(lambda: self._on_reg_letter(' '))
        letter_grid.addWidget(space_btn, 3, 0, 1, 5)
        num_toggle = QPushButton('🔢 数字')
        num_toggle.setMinimumHeight(36)
        num_toggle.setStyleSheet(f"background:{C_BW}; color:#fff; font-size:14px; border-radius:4px;")
        num_toggle.clicked.connect(lambda: self.reg_kb_stack.setCurrentIndex(1))
        letter_grid.addWidget(num_toggle, 3, 5, 1, 5)
        self.reg_kb_stack.addWidget(letter_w)

        # 数字键盘
        num_w = QWidget()
        num_layout = QVBoxLayout(num_w); num_layout.setContentsMargins(0,0,0,0)
        numpad = NumPad()
        numpad.submitted.connect(self._on_reg_key)
        num_layout.addWidget(numpad)
        let_toggle = QPushButton('🔤 字母')
        let_toggle.setFixedHeight(30)
        let_toggle.setStyleSheet(f"background:{C_BW}; color:#fff; font-size:14px; border-radius:4px;")
        let_toggle.clicked.connect(lambda: self.reg_kb_stack.setCurrentIndex(0))
        num_layout.addWidget(let_toggle)
        self.reg_kb_stack.addWidget(num_w)

        layout.addWidget(self.reg_kb_stack)

        # 点击字段切换键盘
        self.reg_active_pwd = self.reg_pwd
        self.reg_name.mousePressEvent = lambda e: (setattr(self, 'reg_active_pwd', None), self.reg_kb_stack.setCurrentIndex(0))
        self.reg_pwd.mousePressEvent = lambda e: (setattr(self, 'reg_active_pwd', self.reg_pwd), self.reg_kb_stack.setCurrentIndex(1))
        self.reg_pwd2.mousePressEvent = lambda e: (setattr(self, 'reg_active_pwd', self.reg_pwd2), self.reg_kb_stack.setCurrentIndex(1))

        reg_btn = QPushButton('注册')
        reg_btn.setMinimumHeight(50)
        reg_btn.setStyleSheet(f"background:{C_JD}; color:#fff; font-size:18px; border-radius:8px;")
        reg_btn.clicked.connect(self._do_register)
        layout.addWidget(reg_btn)

        layout.addSpacing(15)

        nfc_btn = QPushButton('绑定 NFC 卡（可选）')
        nfc_btn.setFixedHeight(40)
        nfc_btn.setStyleSheet(f"background:{C_BG3}; font-size:14px; border-radius:6px; border:1px solid {C_BD};")
        nfc_btn.clicked.connect(self._bind_nfc_after_register)
        layout.addWidget(nfc_btn)

        face_btn = QPushButton('注册人脸（可选）')
        face_btn.setFixedHeight(40)
        face_btn.setStyleSheet(f"background:{C_BG3}; font-size:14px; border-radius:6px; border:1px solid {C_BD};")
        face_btn.clicked.connect(self._start_face_register)
        layout.addWidget(face_btn)

        layout.addStretch()
        self.stack.addWidget(page)

    def _on_reg_letter(self, ch):
        if ch == 'BACK':
            cur = self.reg_name.text()
            self.reg_name.setText(cur[:-1])
        else:
            self.reg_name.setText(self.reg_name.text() + ch)

    def _on_reg_key(self, key):
        pw = self.reg_active_pwd
        if key == 'BACK': pw.setText(pw.text()[:-1])
        elif key == 'ENTER': self._do_register()
        else: pw.setText(pw.text() + key)

    def _do_register(self):
        name = self.reg_name.text().strip()
        pwd = self.reg_pwd.text()
        pwd2 = self.reg_pwd2.text()
        if not name: self._toast('请输入用户名'); return
        if not pwd: self._toast('请输入密码'); return
        if pwd != pwd2: self._toast('两次密码不一致'); return
        for u in self.db.get_all_users():
            if u['name'] == name: self._toast('用户名已存在'); return
        uid = self.db.add_user(name, card_id=None, face_feature=None, permission_level=1, is_admin=0)
        self.db.update_user(uid, password=hashlib.sha256(pwd.encode()).hexdigest())
        self.reg_name.clear(); self.reg_pwd.clear(); self.reg_pwd2.clear()
        self._speak(f'用户 {name} 注册成功')
        self._toast(f'用户 {name} 注册成功')
        self._last_registered_uid = uid

    def _bind_nfc_after_register(self):
        if not hasattr(self, '_last_registered_uid'):
            self._toast('请先注册用户'); return
        self._toast('请将 NFC 卡放到读卡器上...', 0)
        try:
            result = subprocess.run(['nfc-list', '-v'], capture_output=True, text=True, timeout=10)
            uid = None
            for line in result.stdout.split('\n'):
                if 'UID' in line and 'NFCID' in line:
                    uid = line.split(':')[-1].strip().replace(' ', '').upper()
                    if uid and len(uid) >= 8:
                        break
            if uid:
                self.db.update_user(self._last_registered_uid, card_id=uid)
                self._toast(f'NFC 绑定成功: {uid}'); self.overlay.hide()
            else:
                self._toast('未检测到卡片')
        except Exception as e:
            self.overlay.hide(); self._toast('NFC 绑定失败')

    def _start_face_register(self):
        if not hasattr(self, '_last_registered_uid'):
            self._toast('请先注册用户'); return
        self._toast('启动人脸注册...', 0)
        try:
            subprocess.run(
                [sys.executable, '/opt/smart-locker/scripts/face_register_gui.py'],
                timeout=60, cwd='/opt/smart-locker',
                env={**os.environ, 'DISPLAY': ':0', 'REGISTER_USER_ID': str(self._last_registered_uid)}
            )
            self.overlay.hide(); self._toast('人脸注册完成')
            self._start_face_daemon()  # 重启守护进程加载新人脸数据
        except Exception as e:
            self.overlay.hide(); self._toast(f'人脸注册异常')

    # ═══════════════════════════════════
    # PAGE 11: Admin
    # ═══════════════════════════════════
    def _init_admin(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(TitleBar('系统管理', back_cb=self.go_home))

        tabs = QTabWidget()
        tabs.addTab(self._init_inventory_tab(), '库存')
        tabs.addTab(self._init_user_mgmt_tab(), '用户')
        tabs.addTab(self._init_admin_mgmt_tab(), '管理员')
        tabs.addTab(self._init_log_tab(), '日志')
        layout.addWidget(tabs)

        self.stack.addWidget(page)

    # -- inventory --
    def _init_inventory_tab(self):
        w = QWidget(); layout = QVBoxLayout(w); layout.setContentsMargins(10, 10, 10, 10)
        self.inv_table = QTableWidget(); self.inv_table.setColumnCount(5)
        self.inv_table.setHorizontalHeaderLabels(['名称','分类','柜号','库存','条码'])
        self.inv_table.horizontalHeader().setStretchLastSection(True)
        self.inv_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.inv_table.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.inv_table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        layout.addWidget(self.inv_table)

        # Navigation + action buttons
        bottom = QHBoxLayout()
        self.inv_prev = QPushButton('◀')
        self.inv_prev.setFixedSize(50, 40)
        self.inv_prev.setStyleSheet(f"background:{C_BG3}; color:{C_TX}; font-size:16px; border-radius:6px;")
        self.inv_prev.clicked.connect(lambda: self._inv_nav(-1))
        bottom.addWidget(self.inv_prev)
        self.inv_page_lbl = QLabel('1/1')
        self.inv_page_lbl.setAlignment(Qt.AlignCenter)
        self.inv_page_lbl.setStyleSheet(f"color:{C_TX2}; font-size:14px;")
        self.inv_page_lbl.setFixedWidth(60)
        bottom.addWidget(self.inv_page_lbl)
        self.inv_next = QPushButton('▶')
        self.inv_next.setFixedSize(50, 40)
        self.inv_next.setStyleSheet(f"background:{C_BG3}; color:{C_TX}; font-size:16px; border-radius:6px;")
        self.inv_next.clicked.connect(lambda: self._inv_nav(1))
        bottom.addWidget(self.inv_next)
        bottom.addSpacing(10)
        for txt, color, cb in [('新增',C_JD,self._add_component),('编辑',C_BW,self._edit_component),('下架',C_AC,self._delete_component)]:
            btn = QPushButton(txt)
            btn.setStyleSheet(f"background:{color}; color:#fff; padding:8px 12px; border-radius:6px;")
            btn.clicked.connect(cb); bottom.addWidget(btn)
        layout.addLayout(bottom)
        self._inv_page = 0
        return w

    ROWS_PER_PAGE = 8

    def _inv_nav(self, delta):
        comps = self.db.get_all_components()
        total = max(1, (len(comps) + self.ROWS_PER_PAGE - 1) // self.ROWS_PER_PAGE)
        self._inv_page = max(0, min(total - 1, self._inv_page + delta))
        self._refresh_inventory()

    def _refresh_inventory(self):
        comps = self.db.get_all_components()
        total_pages = max(1, (len(comps) + self.ROWS_PER_PAGE - 1) // self.ROWS_PER_PAGE)
        self._inv_page = min(self._inv_page, total_pages - 1)
        start = self._inv_page * self.ROWS_PER_PAGE
        page_comps = comps[start:start + self.ROWS_PER_PAGE]
        self.inv_table.setRowCount(len(page_comps))
        for i, c in enumerate(page_comps):
            self.inv_table.setItem(i,0,QTableWidgetItem(c['name']))
            self.inv_table.setItem(i,1,QTableWidgetItem(c.get('category','')))
            self.inv_table.setItem(i,2,QTableWidgetItem(str(c.get('cabinet_id',''))))
            self.inv_table.setItem(i,3,QTableWidgetItem(str(c.get('stock',0))))
            items = self.db.get_inventory_items(c['id'])
            self.inv_table.setItem(i,4,QTableWidgetItem(f'{len(items)}个'))
        self.inv_table.resizeColumnsToContents()
        self.inv_page_lbl.setText(f'{self._inv_page + 1}/{total_pages}')
        self.inv_prev.setEnabled(self._inv_page > 0)
        self.inv_next.setEnabled(self._inv_page < total_pages - 1)

    def _add_component(self):
        dlg = QDialog(self); dlg.setWindowTitle('新增器件'); dlg.setFixedSize(400,350)
        dlg.setStyleSheet(f"background:{C_BG2};")
        layout = QVBoxLayout(dlg)
        inputs = {}
        for f in ['名称','分类','柜号','库存']:
            layout.addWidget(QLabel(f))
            inp = QLineEdit(); inp.setStyleSheet(f"background:{C_BG3}; color:{C_TX}; padding:6px;"); layout.addWidget(inp)
            inputs[f] = inp
        # 条码行：输入框 + 扫描按钮
        layout.addWidget(QLabel('条码(可选)'))
        bc_row = QHBoxLayout()
        bc_inp = QLineEdit(); bc_inp.setStyleSheet(f"background:{C_BG3}; color:{C_TX}; padding:6px;"); bc_row.addWidget(bc_inp)
        scan_btn = QPushButton('扫码'); scan_btn.setFixedWidth(70)
        scan_btn.setStyleSheet(f"background:{C_BW}; color:#fff; padding:6px; border-radius:4px;")
        scan_btn.clicked.connect(lambda: self._do_scan_fill(bc_inp))
        bc_row.addWidget(scan_btn); layout.addLayout(bc_row)
        inputs['条码(可选)'] = bc_inp

        btn_row = QHBoxLayout()
        ok = QPushButton('确定'); ok.setMinimumHeight(44); ok.setStyleSheet(f"background:{C_JD}; color:#fff; padding:10px 20px; font-size:17px; border-radius:8px;")
        cancel = QPushButton('取消'); cancel.setMinimumHeight(44); cancel.setStyleSheet(f"background:{C_AC}; color:#fff; padding:10px 20px; font-size:17px; border-radius:8px;")
        btn_row.addWidget(ok); btn_row.addWidget(cancel); layout.addLayout(btn_row)
        ok.clicked.connect(dlg.accept); cancel.clicked.connect(dlg.reject)
        if dlg.exec_() == QDialog.Accepted:
            try:
                name = inputs['名称'].text(); cat = inputs['分类'].text()
                cab = int(inputs['柜号'].text() or 0); stock = int(inputs['库存'].text() or 0)
                barcode = inputs['条码(可选)'].text().strip()
                cid = self.db.add_component(name, cat, 0, 0, cab, '', stock)
                if barcode: self.db.add_inventory_item(barcode, cid)
                self._refresh_inventory(); self._toast(f'已添加: {name}')
            except Exception as e: self._toast(f'添加失败: {e}')

    def _edit_component(self):
        row = self.inv_table.currentRow()
        if row < 0: self._toast('请先选择器件'); return
        name = self.inv_table.item(row,0).text()
        comp = None
        for c in self.db.get_all_components():
            if c['name'] == name: comp = c; break
        if not comp: return
        items = self.db.get_inventory_items(comp['id'])
        dlg = QDialog(self); dlg.setWindowTitle(f'编辑 {name}'); dlg.setFixedSize(420, 520)
        dlg.setStyleSheet(f"background:{C_BG2};")
        layout = QVBoxLayout(dlg)
        inputs = {}
        for f, dval in [('名称',comp['name']),('分类',comp.get('category','')),('柜号',str(comp.get('cabinet_id',''))),('库存',str(comp.get('stock',0)))]:
            layout.addWidget(QLabel(f))
            inp = QLineEdit(dval); inp.setStyleSheet(f"background:{C_BG3}; color:{C_TX}; padding:6px;"); layout.addWidget(inp)
            inputs[f] = inp

        # Inventory items section
        layout.addWidget(QLabel('实物条码列表:'))
        items_list = QWidget()
        items_list.setStyleSheet(f"background:{C_BG3}; border-radius:6px;")
        items_layout = QVBoxLayout(items_list)
        items_layout.setSpacing(4)

        def _refresh_items():
            # Clear and rebuild items list
            for j in reversed(range(items_layout.count())):
                w = items_layout.itemAt(j).widget()
                if w: w.deleteLater()
            cur_items = self.db.get_inventory_items(comp['id'])
            for it in cur_items:
                row_w = QWidget()
                row_l = QHBoxLayout(row_w)
                row_l.setContentsMargins(4, 2, 4, 2)
                lbl = QLabel(f"{it['barcode']} ({it['status']})")
                lbl.setStyleSheet(f"color:{C_TX}; font-size:13px; background:transparent;")
                row_l.addWidget(lbl, 1)
                del_btn = QPushButton('删除')
                del_btn.setFixedSize(50, 26)
                del_btn.setStyleSheet(f"background:{C_AC}; color:#fff; font-size:12px; border-radius:4px;")
                del_btn.clicked.connect(lambda checked, bid=it['barcode']: (self.db.remove_inventory_item(bid), _refresh_items()))
                row_l.addWidget(del_btn)
                items_layout.addWidget(row_w)

        _refresh_items()
        layout.addWidget(items_list)

        # Add barcode row
        add_row = QHBoxLayout()
        bc_inp = QLineEdit(''); bc_inp.setPlaceholderText('输入或扫描条码')
        bc_inp.setStyleSheet(f"background:{C_BG3}; color:{C_TX}; padding:6px;"); add_row.addWidget(bc_inp)
        scan_btn = QPushButton('扫码'); scan_btn.setFixedWidth(70)
        scan_btn.setStyleSheet(f"background:{C_BW}; color:#fff; padding:6px; border-radius:4px;")
        scan_btn.clicked.connect(lambda: self._do_scan_fill(bc_inp))
        add_row.addWidget(scan_btn)
        add_btn = QPushButton('添加'); add_btn.setFixedWidth(60)
        add_btn.setStyleSheet(f"background:{C_JD}; color:#fff; padding:6px; border-radius:4px;")
        def _add_item():
            b = bc_inp.text().strip()
            if b:
                try:
                    self.db.add_inventory_item(b, comp['id'])
                    bc_inp.clear()
                    _refresh_items()
                except Exception as e:
                    self._toast(f'添加失败(可能重复): {e}')
        add_btn.clicked.connect(_add_item)
        add_row.addWidget(add_btn)
        layout.addLayout(add_row)

        btn_row = QHBoxLayout()
        ok = QPushButton('保存'); ok.setMinimumHeight(44); ok.setStyleSheet(f"background:{C_JD}; color:#fff; padding:10px 20px; font-size:17px; border-radius:8px;")
        cancel = QPushButton('取消'); cancel.setMinimumHeight(44); cancel.setStyleSheet(f"background:{C_AC}; color:#fff; padding:10px 20px; font-size:17px; border-radius:8px;")
        btn_row.addWidget(ok); btn_row.addWidget(cancel); layout.addLayout(btn_row)
        ok.clicked.connect(dlg.accept); cancel.clicked.connect(dlg.reject)
        if dlg.exec_() == QDialog.Accepted:
            try:
                self.db.update_component(comp['id'],
                    name=inputs['名称'].text(), category=inputs['分类'].text(),
                    cabinet_id=int(inputs['柜号'].text() or 0),
                    stock=int(inputs['库存'].text() or 0))
                self._refresh_inventory(); self._toast('已保存')
            except Exception as e: self._toast(f'保存失败: {e}')

    def _do_scan_fill(self, target_input):
        """扫码并填入条码到输入框"""
        self._toast('请扫描条码...', 0)
        barcode = self._scan_barcode()
        self.overlay.hide()
        if barcode:
            target_input.setText(barcode)
            self._toast(f'已读取: {barcode}')
        else:
            self._toast('扫码超时')

    def _delete_component(self):
        row = self.inv_table.currentRow()
        if row < 0: self._toast('请先选择器件'); return
        name = self.inv_table.item(row,0).text()
        self._confirm_dialog(f'下架 {name}', f'确定下架 {name}？',
            lambda: self._do_delete_component(name))

    def _do_delete_component(self, name):
        for c in self.db.get_all_components():
            if c['name'] == name:
                self.db.delete_component(c['id']); self._refresh_inventory(); self._toast(f'已下架: {name}'); return

    # -- user mgmt --
    def _init_user_mgmt_tab(self):
        w = QWidget(); layout = QVBoxLayout(w); layout.setContentsMargins(10,10,10,10)
        self.user_table = QTableWidget(); self.user_table.setColumnCount(6)
        self.user_table.setHorizontalHeaderLabels(['姓名','权限','密码','NFC','人脸','状态'])
        self.user_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.user_table.horizontalHeader().setStretchLastSection(True)
        self.user_table.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.user_table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        layout.addWidget(self.user_table)

        bottom = QHBoxLayout()
        self.user_prev = QPushButton('◀')
        self.user_prev.setFixedSize(50, 40)
        self.user_prev.setStyleSheet(f"background:{C_BG3}; color:{C_TX}; font-size:16px; border-radius:6px;")
        self.user_prev.clicked.connect(lambda: self._user_nav(-1))
        bottom.addWidget(self.user_prev)
        self.user_page_lbl = QLabel('1/1')
        self.user_page_lbl.setAlignment(Qt.AlignCenter)
        self.user_page_lbl.setStyleSheet(f"color:{C_TX2}; font-size:14px;")
        self.user_page_lbl.setFixedWidth(60)
        bottom.addWidget(self.user_page_lbl)
        self.user_next = QPushButton('▶')
        self.user_next.setFixedSize(50, 40)
        self.user_next.setStyleSheet(f"background:{C_BG3}; color:{C_TX}; font-size:16px; border-radius:6px;")
        self.user_next.clicked.connect(lambda: self._user_nav(1))
        bottom.addWidget(self.user_next)
        bottom.addSpacing(10)
        for txt, color, cb in [
            ('编辑',C_BW,self._edit_user), ('启用/禁用',C_BW,self._toggle_user),
            ('删除',C_AC,self._delete_user), ('NFC绑定',C_BG3,self._admin_bind_nfc),
        ]:
            btn = QPushButton(txt)
            btn.setStyleSheet(f"background:{color}; color:#fff; padding:6px 10px; border-radius:5px; font-size:13px;")
            btn.clicked.connect(cb); bottom.addWidget(btn)
        face_btn = QPushButton('人脸操作')
        face_btn.setStyleSheet(f"background:{C_BG3}; color:{C_TX2}; padding:6px 10px; border-radius:5px; font-size:13px; border:1px solid {C_BD};")
        face_btn.clicked.connect(self._admin_face_op); bottom.addWidget(face_btn)
        bottom.addStretch(); layout.addLayout(bottom)
        self._user_page = 0
        return w

    def _user_nav(self, delta):
        users = self.db.get_all_users()
        total = max(1, (len(users) + self.ROWS_PER_PAGE - 1) // self.ROWS_PER_PAGE)
        self._user_page = max(0, min(total - 1, self._user_page + delta))
        self._refresh_users()

    def _refresh_users(self):
        users = self.db.get_all_users()
        users.sort(key=lambda u: (u.get('is_admin',0) or u.get('permission_level',1) > 1), reverse=True)
        total_pages = max(1, (len(users) + self.ROWS_PER_PAGE - 1) // self.ROWS_PER_PAGE)
        self._user_page = min(self._user_page, total_pages - 1)
        start = self._user_page * self.ROWS_PER_PAGE
        page_users = users[start:start + self.ROWS_PER_PAGE]
        self.user_table.setRowCount(len(page_users))
        for i, u in enumerate(page_users):
            self.user_table.setItem(i,0,QTableWidgetItem(u['name']))
            perm = '管理员' if (u.get('is_admin') or u.get('permission_level',1)>1) else '普通用户'
            self.user_table.setItem(i,1,QTableWidgetItem(perm))
            self.user_table.setItem(i,2,QTableWidgetItem('✓' if (u.get('password') or u.get('admin_password')) else '✗'))
            self.user_table.setItem(i,3,QTableWidgetItem('✓' if u.get('card_id') else '✗'))
            self.user_table.setItem(i,4,QTableWidgetItem('✓' if u.get('face_feature') else '✗'))
            self.user_table.setItem(i,5,QTableWidgetItem('正常' if u.get('account_status',1) else '禁用'))
        self.user_table.resizeColumnsToContents()
        self.user_page_lbl.setText(f'{self._user_page + 1}/{total_pages}')
        self.user_prev.setEnabled(self._user_page > 0)
        self.user_next.setEnabled(self._user_page < total_pages - 1)

    def _get_selected_user(self):
        row = self.user_table.currentRow()
        if row < 0: self._toast('请先选择用户'); return None
        name = self.user_table.item(row,0).text()
        for u in self.db.get_all_users():
            if u['name'] == name: return u
        return None

    def _edit_user(self):
        u = self._get_selected_user()
        if not u: return
        dlg = QDialog(self); dlg.setWindowTitle(f'编辑 {u["name"]}'); dlg.setFixedSize(350,420)
        dlg.setStyleSheet(f"background:{C_BG2};")
        layout = QVBoxLayout(dlg); layout.addWidget(QLabel('新密码（留空不修改）'))
        pw = QLineEdit(); pw.setEchoMode(QLineEdit.Password); pw.setReadOnly(True); layout.addWidget(pw)
        numpad = NumPad()
        numpad.submitted.connect(lambda k: _on_key(k, pw))
        layout.addWidget(numpad)
        btn_row = QHBoxLayout()
        ok = QPushButton('保存'); ok.setMinimumHeight(44); ok.setStyleSheet(f"background:{C_JD}; color:#fff; padding:10px 20px; font-size:17px; border-radius:8px;")
        cancel = QPushButton('取消'); cancel.setMinimumHeight(44); cancel.setStyleSheet(f"background:{C_AC}; color:#fff; padding:10px 20px; font-size:17px; border-radius:8px;")
        btn_row.addWidget(ok); btn_row.addWidget(cancel); layout.addLayout(btn_row)
        ok.clicked.connect(dlg.accept); cancel.clicked.connect(dlg.reject)
        def _on_key(key, pw):
            if key == 'BACK': pw.setText(pw.text()[:-1])
            elif key == 'ENTER': pass
            else: pw.setText(pw.text() + key)
        if dlg.exec_() == QDialog.Accepted and pw.text():
            self.db.update_user(u['id'], password=hashlib.sha256(pw.text().encode()).hexdigest())
            self._refresh_users(); self._toast('密码已更新')

    def _toggle_user(self):
        u = self._get_selected_user()
        if not u: return
        new_status = 0 if u.get('account_status',1) else 1
        self.db.update_user(u['id'], account_status=new_status)
        self._refresh_users(); self._toast('已启用' if new_status else '已禁用')

    def _delete_user(self):
        u = self._get_selected_user()
        if not u: return
        self._confirm_dialog(f'删除 {u["name"]}', f'确定删除用户 {u["name"]}？',
            lambda: (self.db.delete_user(u['id']), self._refresh_users(), self._toast('已删除')))

    def _admin_bind_nfc(self):
        u = self._get_selected_user()
        if not u: return
        self._toast('请将 NFC 卡放到读卡器上...', 0)
        try:
            result = subprocess.run(['nfc-list', '-v'], capture_output=True, text=True, timeout=10)
            for line in result.stdout.split('\n'):
                if 'UID' in line and 'NFCID' in line:
                    uid = line.split(':')[-1].strip().replace(' ', '').upper()
                    if uid and len(uid) >= 8:
                        self.db.update_user(u['id'], card_id=uid)
                        self._refresh_users(); self.overlay.hide()
                        self._toast(f'NFC 绑定成功: {uid}'); return
            self.overlay.hide(); self._toast('未检测到卡片')
        except Exception as e:
            self.overlay.hide(); self._toast('NFC 绑定失败')

    def _admin_face_op(self):
        u = self._get_selected_user()
        if not u: return
        if u.get('face_feature'):
            self._confirm_dialog('删除人脸', f'确定删除 {u["name"]} 的人脸数据？',
                lambda: (self.db.update_user(u['id'], face_feature=None),
                         self._refresh_users(), self._toast('人脸已删除')))
        else:
            # Launch face registration
            self._toast(f'启动人脸注册: {u["name"]}', 0)
            try:
                # Pass user name via environment
                env = {**os.environ, 'DISPLAY': ':0', 'REGISTER_USER_ID': str(u['id'])}
                subprocess.run(
                    [sys.executable, '/opt/smart-locker/scripts/face_register_gui.py'],
                    timeout=60, cwd='/opt/smart-locker', env=env
                )
                self.overlay.hide()
                self._refresh_users()
                self._toast(f'{u["name"]} 人脸注册完成')
                self._start_face_daemon()  # 重启守护进程加载新人脸数据
            except Exception as e:
                self.overlay.hide()
                self._toast(f'人脸注册未完成')

    # -- admin mgmt --
    def _init_admin_mgmt_tab(self):
        w = QWidget(); layout = QVBoxLayout(w); layout.setContentsMargins(10,10,10,10)
        layout.addWidget(QLabel('管理员授权管理'))
        self.admin_table = QTableWidget(); self.admin_table.setColumnCount(3)
        self.admin_table.setHorizontalHeaderLabels(['姓名','权限','操作'])
        self.admin_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.admin_table.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.admin_table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        layout.addWidget(self.admin_table)

        bottom = QHBoxLayout()
        self.admin_prev = QPushButton('◀')
        self.admin_prev.setFixedSize(50, 40)
        self.admin_prev.setStyleSheet(f"background:{C_BG3}; color:{C_TX}; font-size:16px; border-radius:6px;")
        self.admin_prev.clicked.connect(lambda: self._admin_nav(-1))
        bottom.addWidget(self.admin_prev)
        self.admin_page_lbl = QLabel('1/1')
        self.admin_page_lbl.setAlignment(Qt.AlignCenter)
        self.admin_page_lbl.setStyleSheet(f"color:{C_TX2}; font-size:14px;")
        self.admin_page_lbl.setFixedWidth(60)
        bottom.addWidget(self.admin_page_lbl)
        self.admin_next = QPushButton('▶')
        self.admin_next.setFixedSize(50, 40)
        self.admin_next.setStyleSheet(f"background:{C_BG3}; color:{C_TX}; font-size:16px; border-radius:6px;")
        self.admin_next.clicked.connect(lambda: self._admin_nav(1))
        bottom.addWidget(self.admin_next)
        bottom.addSpacing(10)
        promote = QPushButton('设为管理员'); promote.setStyleSheet(f"background:{C_JD}; color:#fff; padding:8px; border-radius:6px;")
        promote.clicked.connect(lambda: self._set_admin(True)); bottom.addWidget(promote)
        demote = QPushButton('撤销管理员'); demote.setStyleSheet(f"background:{C_AC}; color:#fff; padding:8px; border-radius:6px;")
        demote.clicked.connect(lambda: self._set_admin(False)); bottom.addWidget(demote)
        bottom.addStretch(); layout.addLayout(bottom)
        self._admin_page = 0
        return w

    def _admin_nav(self, delta):
        users = self.db.get_all_users()
        total = max(1, (len(users) + self.ROWS_PER_PAGE - 1) // self.ROWS_PER_PAGE)
        self._admin_page = max(0, min(total - 1, self._admin_page + delta))
        self._refresh_admin_table()

    def _refresh_admin_table(self):
        users = self.db.get_all_users()
        users.sort(key=lambda u: (u.get('is_admin',0) or u.get('permission_level',1)>1), reverse=True)
        total_pages = max(1, (len(users) + self.ROWS_PER_PAGE - 1) // self.ROWS_PER_PAGE)
        self._admin_page = min(self._admin_page, total_pages - 1)
        start = self._admin_page * self.ROWS_PER_PAGE
        page_users = users[start:start + self.ROWS_PER_PAGE]
        self.admin_table.setRowCount(len(page_users))
        for i, u in enumerate(page_users):
            self.admin_table.setItem(i,0,QTableWidgetItem(u['name']))
            is_admin = u.get('is_admin') or u.get('permission_level',1)>1
            self.admin_table.setItem(i,1,QTableWidgetItem('管理员' if is_admin else '普通用户'))
            self.admin_table.setItem(i,2,QTableWidgetItem('撤销' if is_admin else '授权'))
        self.admin_page_lbl.setText(f'{self._admin_page + 1}/{total_pages}')
        self.admin_prev.setEnabled(self._admin_page > 0)
        self.admin_next.setEnabled(self._admin_page < total_pages - 1)

    def _set_admin(self, make_admin):
        row = self.admin_table.currentRow()
        if row < 0: self._toast('请先选择用户'); return
        name = self.admin_table.item(row,0).text()
        for u in self.db.get_all_users():
            if u['name'] == name:
                self.db.update_user(u['id'], is_admin=1 if make_admin else 0,
                                   permission_level=2 if make_admin else 1)
                self._refresh_admin_table(); self._refresh_users()
                self._toast(f'{name} 已{"授权" if make_admin else "撤销"}'); return

    # -- logs --
    def _init_log_tab(self):
        w = QWidget(); layout = QVBoxLayout(w); layout.setContentsMargins(10,10,10,10)
        self.log_table = QTableWidget(); self.log_table.setColumnCount(6)
        self.log_table.setHorizontalHeaderLabels(['借用人','器件','柜号','借出时间','归还时间','状态'])
        self.log_table.horizontalHeader().setStretchLastSection(True)
        self.log_table.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.log_table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        layout.addWidget(self.log_table)

        bottom = QHBoxLayout()
        self.log_prev = QPushButton('◀')
        self.log_prev.setFixedSize(50, 40)
        self.log_prev.setStyleSheet(f"background:{C_BG3}; color:{C_TX}; font-size:16px; border-radius:6px;")
        self.log_prev.clicked.connect(lambda: self._log_nav(-1))
        bottom.addWidget(self.log_prev)
        self.log_page_lbl = QLabel('1/1')
        self.log_page_lbl.setAlignment(Qt.AlignCenter)
        self.log_page_lbl.setStyleSheet(f"color:{C_TX2}; font-size:14px;")
        self.log_page_lbl.setFixedWidth(60)
        bottom.addWidget(self.log_page_lbl)
        self.log_next = QPushButton('▶')
        self.log_next.setFixedSize(50, 40)
        self.log_next.setStyleSheet(f"background:{C_BG3}; color:{C_TX}; font-size:16px; border-radius:6px;")
        self.log_next.clicked.connect(lambda: self._log_nav(1))
        bottom.addWidget(self.log_next)
        bottom.addSpacing(10)
        refresh = QPushButton('刷新'); refresh.setStyleSheet(f"background:{C_BW}; color:#fff; padding:8px 12px; border-radius:6px;")
        refresh.clicked.connect(self._refresh_logs); bottom.addWidget(refresh)
        bottom.addStretch(); layout.addLayout(bottom)
        self._log_page = 0
        return w

    def _log_nav(self, delta):
        all_records = []
        for u in self.db.get_all_users():
            for r in self.db.get_user_records(u['id']):
                r['_user_name'] = u['name']
                all_records.append(r)
        all_records.sort(key=lambda r: r.get('borrow_time',''), reverse=True)
        total = max(1, (len(all_records) + self.ROWS_PER_PAGE - 1) // self.ROWS_PER_PAGE)
        self._log_page = max(0, min(total - 1, self._log_page + delta))
        self._refresh_logs()

    def _refresh_logs(self):
        all_records = []
        for u in self.db.get_all_users():
            for r in self.db.get_user_records(u['id']):
                r['_user_name'] = u['name']; all_records.append(r)
        all_records.sort(key=lambda r: r.get('borrow_time',''), reverse=True)
        total_pages = max(1, (len(all_records) + self.ROWS_PER_PAGE - 1) // self.ROWS_PER_PAGE)
        self._log_page = min(self._log_page, total_pages - 1)
        start = self._log_page * self.ROWS_PER_PAGE
        page_records = all_records[start:start + self.ROWS_PER_PAGE]
        self.log_table.setRowCount(len(page_records))
        for i, r in enumerate(page_records):
            comp = self.db.get_component(r['component_id'])
            name = comp['name'] if comp else '?'
            self.log_table.setItem(i,0,QTableWidgetItem(r.get('_user_name','?')))
            self.log_table.setItem(i,1,QTableWidgetItem(name))
            self.log_table.setItem(i,2,QTableWidgetItem(str(r.get('cabinet_id',''))))
            self.log_table.setItem(i,3,QTableWidgetItem(r.get('borrow_time','')))
            self.log_table.setItem(i,4,QTableWidgetItem(r.get('return_time','')))
            item = QTableWidgetItem(r['status'])
            item.setForeground(QColor(C_AC if r['status']=='borrowed' else C_JD))
            self.log_table.setItem(i,5,item)
        self.log_table.resizeColumnsToContents()
        self.log_page_lbl.setText(f'{self._log_page + 1}/{total_pages}')
        self.log_prev.setEnabled(self._log_page > 0)
        self.log_next.setEnabled(self._log_page < total_pages - 1)


# ═══════════════════════════════════
def main():
    os.environ['DISPLAY'] = ':0'
    app = QApplication(sys.argv)
    app.setStyleSheet(STYLE)
    win = MainWindow()
    win.show(); win.showFullScreen()
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()
