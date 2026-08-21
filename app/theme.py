"""主题系统：浅色 / 深色 / 跟随系统（默认浅色）。

控件通过 QSS 角色属性着色：
- 卡片内 QLabel：role="name"/"cap"/"balance"/"type"，status="ok"/"err"/"busy"/"idle"
- 主窗口标题：role="apptitle"/"appsubtitle"，提示文字 role="hint"
"""

from __future__ import annotations

from PySide6.QtWidgets import QApplication

LIGHT_QSS = """
QMainWindow, QDialog { background: #f0f2f5; }
QMenuBar { background: #f0f2f5; }
QMenuBar::item { padding: 4px 10px; border-radius: 6px; background: transparent; color: #3c4048; }
QMenuBar::item:selected { background: #e3e6ea; }
QMenu { background: #ffffff; border: 1px solid #e3e6ea; border-radius: 8px; padding: 4px; }
QMenu::item { padding: 6px 22px; border-radius: 5px; color: #1f2328; }
QMenu::item:selected { background: #eef1ff; color: #3d5af0; }
QStatusBar { background: #f0f2f5; color: #6b7280; }
QScrollArea { background: transparent; border: none; }
QScrollArea > QWidget > QWidget { background: transparent; }

QPushButton, QToolButton {
    border: 1px solid #d9dde3; border-radius: 6px; padding: 7px 14px;
    font-size: 13px; color: #3c4048; background: #ffffff;
}
QPushButton:hover, QToolButton:hover { background: #f3f4f6; }
QPushButton:pressed, QToolButton:pressed { background: #e9ebef; }

QPushButton#primaryBtn {
    background: #4d6bfe; color: #ffffff; border: none; font-weight: 600;
}
QPushButton#primaryBtn:hover { background: #3d5af0; }
QPushButton#primaryBtn:pressed { background: #3350e0; }

QToolButton#secondaryBtn { background: #ffffff; }
QToolButton#secondaryBtn:checked { background: #4d6bfe; color: #ffffff; border-color: #4d6bfe; }

QPushButton#cardBtn {
    padding: 4px 10px; font-size: 12px; border-radius: 5px;
    background: #ffffff; border: 1px solid #d9dde3; color: #4a4f57;
}
QPushButton#cardBtn:hover { background: #f3f4f6; }

QLineEdit, QSpinBox, QComboBox {
    border: 1px solid #d9dde3; border-radius: 6px; padding: 6px 8px;
    background: #ffffff; font-size: 13px; color: #1f2328;
    selection-background-color: #4d6bfe;
}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus { border-color: #4d6bfe; }

QDialogButtonBox QPushButton { min-width: 72px; }
QMessageBox { background: #ffffff; }

#siteCard { background: #ffffff; border: 1px solid #e3e6ea; border-radius: 10px; }
#siteCard QLabel[role="name"] { font-size: 14px; font-weight: bold; color: #1f2328; }
#siteCard QLabel[role="cap"] { font-size: 11px; color: #8a919c; }
#siteCard QLabel[role="balance"] { font-size: 18px; font-weight: bold; color: #1f2328; }
#siteCard QLabel[role="type"] { font-size: 11px; color: #4d6bfe; }
#siteCard QLabel[status="ok"] { color: #1a7f37; font-size: 12px; }
#siteCard QLabel[status="err"] { color: #c62828; font-size: 12px; }
#siteCard QLabel[status="busy"] { color: #9e6a03; font-size: 12px; }
#siteCard QLabel[status="idle"] { color: #555555; font-size: 12px; }
QLabel[role="apptitle"] { font-size: 16px; font-weight: bold; color: #1f2328; }
QLabel[role="appsubtitle"] { font-size: 11px; color: #8a919c; }
QLabel[role="hint"] { color: #999999; font-size: 13px; }
"""

DARK_QSS = """
QMainWindow, QDialog { background: #1e1f24; }
QMenuBar { background: #1e1f24; }
QMenuBar::item { padding: 4px 10px; border-radius: 6px; background: transparent; color: #d6d6dc; }
QMenuBar::item:selected { background: #33343a; }
QMenu { background: #2c2d33; border: 1px solid #3a3b41; border-radius: 8px; padding: 4px; }
QMenu::item { padding: 6px 22px; border-radius: 5px; color: #e6e6ea; }
QMenu::item:selected { background: #34364a; color: #9db4ff; }
QStatusBar { background: #1e1f24; color: #9a9aa0; }
QScrollArea { background: transparent; border: none; }
QScrollArea > QWidget > QWidget { background: transparent; }

QPushButton, QToolButton {
    border: 1px solid #3f4047; border-radius: 6px; padding: 7px 14px;
    font-size: 13px; color: #e6e6ea; background: #2c2d33;
}
QPushButton:hover, QToolButton:hover { background: #34353c; }
QPushButton:pressed, QToolButton:pressed { background: #3a3b42; }

QPushButton#primaryBtn {
    background: #4d6bfe; color: #ffffff; border: none; font-weight: 600;
}
QPushButton#primaryBtn:hover { background: #6079ff; }
QPushButton#primaryBtn:pressed { background: #3d5af0; }

QToolButton#secondaryBtn { background: #2c2d33; }
QToolButton#secondaryBtn:checked { background: #4d6bfe; color: #ffffff; border-color: #4d6bfe; }

QPushButton#cardBtn {
    padding: 4px 10px; font-size: 12px; border-radius: 5px;
    background: #2c2d33; border: 1px solid #3f4047; color: #b9bac0;
}
QPushButton#cardBtn:hover { background: #34353c; }

QLineEdit, QSpinBox, QComboBox {
    border: 1px solid #3f4047; border-radius: 6px; padding: 6px 8px;
    background: #2c2d33; font-size: 13px; color: #e6e6ea;
    selection-background-color: #4d6bfe;
}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus { border-color: #4d6bfe; }

QDialogButtonBox QPushButton { min-width: 72px; }
QMessageBox { background: #2c2d33; }

#siteCard { background: #2c2d33; border: 1px solid #3a3b41; border-radius: 10px; }
#siteCard QLabel[role="name"] { font-size: 14px; font-weight: bold; color: #e6e6ea; }
#siteCard QLabel[role="cap"] { font-size: 11px; color: #9a9aa0; }
#siteCard QLabel[role="balance"] { font-size: 18px; font-weight: bold; color: #f0f0f4; }
#siteCard QLabel[role="type"] { font-size: 11px; color: #8fa8ff; }
#siteCard QLabel[status="ok"] { color: #4caf50; font-size: 12px; }
#siteCard QLabel[status="err"] { color: #ef5350; font-size: 12px; }
#siteCard QLabel[status="busy"] { color: #d4a72c; font-size: 12px; }
#siteCard QLabel[status="idle"] { color: #8a8a8e; font-size: 12px; }
QLabel[role="apptitle"] { font-size: 16px; font-weight: bold; color: #e6e6ea; }
QLabel[role="appsubtitle"] { font-size: 11px; color: #9a9aa0; }
QLabel[role="hint"] { color: #8a8a8e; font-size: 13px; }
"""


def resolve_theme(app: QApplication, config_theme: str) -> str:
    """解析实际生效的主题：system 时跟随系统深浅色。"""
    if config_theme == "system":
        from PySide6.QtCore import Qt
        try:
            scheme = app.styleHints().colorScheme()
            return "dark" if scheme == Qt.ColorScheme.Dark else "light"
        except Exception:  # noqa: BLE001 —— 旧版 Qt 不支持时回退浅色
            return "light"
    return config_theme


def apply_theme(app: QApplication, config_theme: str) -> str:
    """应用主题 QSS，返回实际生效的主题（light/dark）。"""
    effective = resolve_theme(app, config_theme)
    app.setStyleSheet(DARK_QSS if effective == "dark" else LIGHT_QSS)
    return effective
