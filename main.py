"""API 额度监控器 —— 入口。

运行：python main.py
打包：build.bat（或 pyinstaller --onefile --windowed --name "API余额查询程序" main.py）
"""

import logging
import os
import sys

from PySide6.QtCore import QLockFile
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMessageBox

from app.config import app_dir
from app.main_window import MainWindow


def resource_path(name: str) -> str:
    """打包后资源在 _MEIPASS 下，源码运行时在项目目录下。"""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, name)


def setup_logging():
    """windowed 模式没有控制台，日志写入程序目录 app.log 便于排查。"""
    try:
        log_path = os.path.join(app_dir(), "app.log")
        logging.basicConfig(
            filename=log_path, level=logging.WARNING,
            format="%(asctime)s %(levelname)s %(name)s: %(message)s",
            encoding="utf-8",
        )
    except OSError:
        logging.basicConfig(level=logging.WARNING)


def load_app_fonts() -> str | None:
    """加载内置的 Maple Mono NF CN 字体（hinted 低分辨率优化版），返回家族名。"""
    from PySide6.QtGui import QFontDatabase

    db = QFontDatabase()
    family = None
    for fname in ("MapleMono-NF-CN-Regular.ttf", "MapleMono-NF-CN-Bold.ttf"):
        p = resource_path(os.path.join("assets", "fonts", fname))
        if os.path.exists(p):
            fid = db.addApplicationFont(p)
            if fid >= 0:
                fams = db.applicationFontFamilies(fid)
                if fams and family is None:
                    family = fams[0]
    return family


def acquire_single_instance_lock(app: QApplication) -> QLockFile | None:
    """单实例锁：防止双开时两个实例互相覆盖配置。

    返回 None 表示已有实例在运行（调用方应退出）。
    """
    lock = QLockFile(os.path.join(app_dir(), "api-quota-monitor.lock"))
    lock.setStaleLockTime(0)  # 进程崩溃后锁自动失效
    if lock.tryLock(100):
        return lock
    QMessageBox.information(None, "提示", "API 额度监控器已在运行，请勿重复打开。")
    return None


def main() -> int:
    setup_logging()
    app = QApplication(sys.argv)
    app.setApplicationName("ApiQuotaMonitor")
    app.setStyle("Fusion")

    # 内置 Maple Mono NF CN（hinted 低分辨率优化版）字体
    from PySide6.QtGui import QFont
    family = load_app_fonts()
    if family:
        app.setFont(QFont(family, 10))

    lock = acquire_single_instance_lock(app)
    if lock is None:
        return 0

    icon_path = resource_path(os.path.join("assets", "app.ico"))
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    window = MainWindow()
    window.show()
    try:
        return app.exec()
    finally:
        lock.unlock()  # 正常退出释放锁


if __name__ == "__main__":
    sys.exit(main())
