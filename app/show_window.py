"""展示窗口：背景图（默认 = 图片的 30% 大小）+ 文字叠加。

- 无边框独立窗口，背景图铺满窗口并随窗口缩放（cover 等比裁切居中）
- 可拖动；可拖边缘/右下角手柄调整大小（大小会被记住）
- 单击任意位置刷新数据；每 60 秒自动刷新
- 左上角固定「返回」按钮（位置稳定不随缩放乱跑）：关闭展示窗口、恢复主窗口
"""

from __future__ import annotations

import os
import sys

from PySide6.QtCore import QPoint, QRect, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QFontMetrics, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QWidget

from .providers.base import QuotaInfo
from .worker import TestBridge, TestTask

AUTO_REFRESH_MS = 60_000  # 60 秒自动刷新（参考 dsh-whale-balance）

BG_NAME = "background.png"   # 打包资源里的背景图
BG_RATIO = 0.30              # 默认窗口大小 = 背景图尺寸的 30%
MIN_W, MIN_H = 160, 180
EDGE = 10  # 边缘拖拽调整大小的感应宽度

# 边缘方向位
LEFT, RIGHT, TOP, BOTTOM = 1, 2, 4, 8

# 返回按钮：锚定右上角固定位置（不随窗口缩放乱跑；右上角是图里的留空区）
BACK_SIZE = 28


def _resource(name: str) -> str:
    """打包后资源在 _MEIPASS 下，源码运行时在项目目录下。"""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(base, name)


def currency_symbol(currency: str) -> str:
    """币种文本 → 符号；未知币种原样返回。"""
    return {
        "CNY": "¥", "RMB": "¥", "JPY": "¥",
        "USD": "$", "EUR": "€", "GBP": "£",
        "KRW": "₩", "HKD": "HK$", "TWD": "NT$",
    }.get((currency or "").upper(), currency or "")


def fmt_amount(v, currency=""):
    if v is None:
        return "-"
    try:
        f = float(v)
    except (TypeError, ValueError):
        return "-"
    s = f"{f:,.2f}" if abs(f) >= 1 else f"{f:.4f}"
    return f"{currency_symbol(currency)}{s}"


class ShowWindow(QWidget):
    """站名 + 余额的独立展示窗口（背景图为底）。"""

    def __init__(self, entry: dict, initial_info: QuotaInfo | None = None,
                 on_close=None, parent=None, initial_size: tuple[int, int] | None = None):
        super().__init__(parent)
        self.entry = entry
        self._info = initial_info
        self._on_close = on_close
        self._closed = False
        self._busy = False
        self._status = "点击任意位置刷新"

        # 加载背景图（不做透明处理，整体不透明显示）
        self._bg_pixmap = QPixmap()
        bg_path = _resource(os.path.join("assets", BG_NAME))
        if os.path.exists(bg_path):
            img = QImage(bg_path)
            if not img.isNull():
                self._bg_pixmap = QPixmap.fromImage(img)

        # 默认大小 = 背景图的 30%
        if not self._bg_pixmap.isNull():
            def_w = int(self._bg_pixmap.width() * BG_RATIO)
            def_h = int(self._bg_pixmap.height() * BG_RATIO)
        else:
            def_w, def_h = 308, 308
        self._default_size = (max(def_w, MIN_W), max(def_h, MIN_H))

        self.setWindowTitle("余额展示")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        # 窗口透明：背景图 png 自带的透明区域（无像素处）显示为透明
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setMinimumSize(MIN_W, MIN_H)
        if initial_size:
            w, h = max(int(initial_size[0]), MIN_W), max(int(initial_size[1]), MIN_H)
        else:
            w, h = self._default_size
        s = max(w, h)
        self.resize(s, s)  # 固定 1:1（背景图为正方形）
        self.setMouseTracking(True)

        self._back_rect = QRectF()
        self._press_pos: QPoint | None = None
        self._press_global: QPoint | None = None
        self._moved = False
        self._resize_dir = 0
        self._orig_geo: QRect | None = None
        self._resizing = False

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh)
        self._timer.start(AUTO_REFRESH_MS)

        if initial_info is not None:
            self._apply_info(initial_info)
        else:
            self._refresh()  # 首次打开立即刷新

    def resizeEvent(self, event):
        """固定 1:1 长宽比例（与背景图一致），防止拖变形。"""
        s = max(self.width(), self.height())
        if (self.width() != s or self.height() != s) and not self._resizing:
            self._resizing = True
            self.resize(s, s)
            self._resizing = False
        super().resizeEvent(event)

    # ============ 数据刷新 ============
    def _refresh(self):
        if self._busy:
            return
        self._busy = True
        self._status = "刷新中…"
        self.update()
        bridge = TestBridge()
        bridge.done.connect(self._on_done)
        from PySide6.QtCore import QThreadPool
        QThreadPool.globalInstance().start(TestTask(self.entry, bridge))

    def _on_done(self, info: QuotaInfo):
        self._busy = False
        self._apply_info(info)

    def _apply_info(self, info: QuotaInfo):
        self._info = info
        if info.ok:
            self._status = "数据正常"
        else:
            self._status = info.message or "查询失败"
        self.update()

    # ============ 绘制 ============
    def _draw_text(self, p, font, rect, flags, text, color,
                   halo=QColor(0, 0, 0, 150), halo_off=1):
        """带阴影描边的文字，完整绘制、绝不裁剪（超出矩形也完整显示在上层）。"""
        flags = flags | Qt.TextFlag.TextDontClip
        p.setFont(font)
        p.setPen(halo)
        p.drawText(rect.translated(halo_off, halo_off), flags, text)
        p.drawText(rect.translated(-halo_off, -halo_off), flags, text)
        p.setPen(color)
        p.drawText(rect, flags, text)

    def paintEvent(self, event):
        p = QPainter(self)
        try:
            self._paint(p)
        except Exception:
            # 绘制异常绝不崩溃：记录日志并结束绘制
            import logging
            logging.getLogger(__name__).exception("展示窗口绘制异常")
        finally:
            p.end()

    def _paint(self, p: QPainter):
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        rect = QRectF(0, 0, w, h)

        # —— 背景图：cover 等比缩放铺满窗口，随窗口缩放 ——
        if not self._bg_pixmap.isNull():
            iw, ih = self._bg_pixmap.width(), self._bg_pixmap.height()
            s = max(w / iw, h / ih)  # cover：填满整个窗口
            dw = iw * s
            dh = ih * s
            x = (w - dw) / 2
            y = (h - dh) / 2
            # 注意：PySide6 的 drawPixmap 不支持 (QRectF, QPixmap) 两参数，
            # 必须带源区域（三参数形式）
            p.drawPixmap(QRectF(x, y, dw, dh), self._bg_pixmap, QRectF(0, 0, iw, ih))
        else:
            # 兜底：渐变背景（铺满，无透明边缘外露）
            from PySide6.QtGui import QLinearGradient
            grad = QLinearGradient(0, 0, 0, h)
            grad.setColorAt(0.0, QColor("#3d5af0"))
            grad.setColorAt(1.0, QColor("#24317a"))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(grad)
            p.drawRect(rect)

        # 等比缩放因子（文字随窗口缩放）
        scale = min(w / self._default_size[0], h / self._default_size[1])
        scale = max(scale, 0.5)

        def px(base: float) -> int:
            return max(int(round(base * scale)), 8)

        # 深蓝文字（气泡内白底，深色对比清晰）
        ink = QColor("#1F3A5F")
        ink_light = QColor("#3D5A80")
        halo = QColor(255, 255, 255, 210)

        # 文字块中心对齐气泡实际中心（气泡 x 7%-83%，中心约 45%）
        center_x = w * 0.45
        text_w = w * 0.34
        text_x = center_x - text_w / 2

        # 文字固定字号，不收缩；drawText 默认不裁剪，
        # 超出文字区时完整绘制并盖在背景/角色之上
        # 第一行：站点名称（去掉空格）+ “余额”二字（字号稍小）
        import re
        raw_name = self.entry.get("display_name") or "未命名站点"
        name = re.sub(r"\s+", "", raw_name)
        f = QFont(self.font())
        f.setPixelSize(px(20))
        f.setBold(True)
        f_small = QFont(self.font())
        f_small.setPixelSize(px(14))
        f_small.setBold(True)
        fm = QFontMetrics(f)
        fm_s = QFontMetrics(f_small)
        name_w = fm.horizontalAdvance(name)
        suffix_w = fm_s.horizontalAdvance("余额")
        gap = 2
        line_rect = QRectF(text_x, h * 0.10, text_w, h * 0.11)
        start_x = line_rect.center().x() - (name_w + gap + suffix_w) / 2
        cy_top = line_rect.top()
        cy_h = line_rect.height()
        self._draw_text(p, f, QRectF(start_x, cy_top, name_w, cy_h),
                        Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                        name, ink, halo)
        self._draw_text(p, f_small, QRectF(start_x + name_w + gap, cy_top, suffix_w, cy_h),
                        Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                        "余额", ink_light, halo)

        # 第二行：余额具体数字 + 币种（大字）
        if self._info is not None:
            val = self._info.remaining if self._info.remaining is not None else self._info.total
            bal = fmt_amount(val, self._info.currency or "")
        else:
            bal = "-"
        f3 = QFont(self.font())
        f3.setPixelSize(px(36))
        f3.setBold(True)
        self._draw_text(p, f3, QRectF(text_x, h * 0.21, text_w, h * 0.15),
                        Qt.AlignmentFlag.AlignCenter, bal, ink, halo)

        # 第三行：数据状态
        f4 = QFont(self.font())
        f4.setPixelSize(px(13))
        self._draw_text(p, f4, QRectF(text_x, h * 0.355, text_w, h * 0.10),
                        Qt.AlignmentFlag.AlignCenter, self._status, ink_light, halo)

        # —— 返回按钮：固定在右上角、固定大小，不侵占气泡（气泡最右约 60% 宽） ——
        br = QRectF(w - BACK_SIZE - 12, 12, BACK_SIZE, BACK_SIZE)
        p.setPen(QPen(QColor(31, 58, 95, 140), 1))
        p.setBrush(QColor(255, 255, 255, 170))
        p.drawEllipse(br)
        f6 = QFont(self.font())
        f6.setPixelSize(int(BACK_SIZE * 0.56))
        p.setFont(f6)
        p.setPen(QColor("#1F3A5F"))
        p.drawText(br, Qt.AlignmentFlag.AlignCenter, "↩")
        self._back_rect = br

    # ============ 鼠标交互 ============
    def _hit_test_edge(self, pos: QPoint) -> int:
        """判断点是否落在可调整大小的边缘区域。"""
        w, h = self.width(), self.height()
        x, y = pos.x(), pos.y()
        d = 0
        if x <= EDGE:
            d |= LEFT
        if x >= w - EDGE:
            d |= RIGHT
        if y <= EDGE:
            d |= TOP
        if y >= h - EDGE:
            d |= BOTTOM
        return d

    @staticmethod
    def _resize_cursor(d: int) -> Qt.CursorShape:
        if d in (LEFT | TOP, RIGHT | BOTTOM):
            return Qt.CursorShape.SizeFDiagCursor
        if d in (RIGHT | TOP, LEFT | BOTTOM):
            return Qt.CursorShape.SizeBDiagCursor
        if d in (LEFT, RIGHT):
            return Qt.CursorShape.SizeHorCursor
        if d in (TOP, BOTTOM):
            return Qt.CursorShape.SizeVerCursor
        return Qt.CursorShape.ArrowCursor

    def mousePressEvent(self, event):
        # 边缘区域 → 进入调整大小模式
        self._resize_dir = self._hit_test_edge(event.position().toPoint())
        if self._resize_dir:
            self._press_global = event.globalPosition().toPoint()
            self._orig_geo = QRect(self.geometry())
            return
        if self._back_rect.contains(event.position().toPoint()):
            self._back()
            return
        self._press_pos = event.position().toPoint()
        self._press_global = event.globalPosition().toPoint()
        self._moved = False

    def mouseMoveEvent(self, event):
        # 调整大小
        if self._resize_dir:
            gp = event.globalPosition().toPoint()
            dx = gp.x() - self._press_global.x()
            dy = gp.y() - self._press_global.y()
            g = QRect(self._orig_geo)
            if self._resize_dir & LEFT:
                g.setLeft(g.left() + dx)
            if self._resize_dir & RIGHT:
                g.setRight(g.right() + dx)
            if self._resize_dir & TOP:
                g.setTop(g.top() + dy)
            if self._resize_dir & BOTTOM:
                g.setBottom(g.bottom() + dy)
            self.setGeometry(g)
            return
        # 拖动窗口
        if self._press_global is not None:
            delta = event.globalPosition().toPoint() - self._press_global
            self.move(self.pos() + delta)
            self._press_global = event.globalPosition().toPoint()
            self._moved = True
        else:
            # 悬停时按边缘位置更新光标
            self.setCursor(self._resize_cursor(self._hit_test_edge(event.position().toPoint())))

    def mouseReleaseEvent(self, event):
        if self._resize_dir:
            self._resize_dir = 0
            self._press_global = None
            self._orig_geo = None
            self.setCursor(Qt.CursorShape.ArrowCursor)
            return
        if not self._moved and self._press_pos is not None:
            self._refresh()  # 单击任意位置刷新
        self._press_pos = None
        self._press_global = None
        self.setCursor(Qt.CursorShape.ArrowCursor)

    # ============ 返回 ============
    def _back(self):
        self.close()

    def closeEvent(self, event):
        self._timer.stop()
        if self._on_close is not None:
            cb = self._on_close
            self._on_close = None  # 防止重复调用
            cb((self.width(), self.height()))  # 把最后的大小交回主窗口保存
        super().closeEvent(event)
