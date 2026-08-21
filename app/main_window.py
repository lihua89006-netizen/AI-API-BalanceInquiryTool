"""主窗口：置顶按钮 + 站点额度卡片列表 + 刷新控制。"""

from __future__ import annotations

import math
import time
import uuid

from PySide6.QtCore import QByteArray, Qt, QThreadPool, QTimer, QUrl
from PySide6.QtGui import QActionGroup, QDesktopServices, QFontMetrics
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .config import Config, load_config
from .providers import list_provider_classes
from .providers.base import Provider, QuotaInfo, NUMBER, PASSWORD, TEXT
from .theme import apply_theme
from .worker import Refresher, TestBridge, TestTask

def fmt_money(v: float | None, currency: str = "") -> str:
    if v is None:
        return "-"
    try:
        f = float(v)
    except (TypeError, ValueError):
        return "-"
    if not math.isfinite(f):
        return "-"
    s = f"{f:,.2f}" if abs(f) >= 1 else f"{f:.4f}"
    return f"{s} {currency}".strip()


class SiteCard(QFrame):
    """一个站点的一张卡片。"""

    def __init__(self, entry: dict, on_refresh, on_edit, on_delete, on_move=None,
                 on_show=None, parent=None):
        super().__init__(parent)
        self.entry = entry
        self.uid = entry.get("uid") or entry.get("provider_id", "")
        self.on_refresh = on_refresh
        self.on_edit = on_edit
        self.on_delete = on_delete
        self.on_move = on_move
        self.on_show = on_show

        self.setObjectName("siteCard")

        root = QHBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 12)
        root.setSpacing(16)

        # —— 左侧：名称 + 类型（可点击跳转网站），固定宽度保证余额列对齐 ——
        LEFT_W = 160
        left = QVBoxLayout()
        left.setSpacing(4)
        self.name_label = QLabel()
        self.name_label.setProperty("role", "name")
        self.name_label.setFixedWidth(LEFT_W)
        self._elide(self.name_label, entry.get("display_name") or "未命名站点", LEFT_W)
        left.addWidget(self.name_label)
        self.type_label = QLabel()
        self.type_label.setProperty("role", "type")
        self.type_label.setFixedWidth(LEFT_W)
        self.type_label.setToolTip("点击打开该网站")
        self.type_label.setTextInteractionFlags(Qt.TextInteractionFlag.LinksAccessibleByMouse)
        self.type_label.linkActivated.connect(self._open_site)
        left.addWidget(self.type_label)
        root.addLayout(left, 0)

        # —— 中间：余额（单行大字，币种跟在数字后面） ——
        middle = QVBoxLayout()
        middle.setSpacing(2)
        cap = QLabel("余额")
        cap.setProperty("role", "cap")
        middle.addWidget(cap)
        self.balance_label = QLabel("-")
        self.balance_label.setProperty("role", "balance")
        middle.addWidget(self.balance_label)
        middle.addStretch(1)
        root.addLayout(middle, 1)

        # —— 右侧：状态 + 按钮（两行） ——
        right = QVBoxLayout()
        right.setSpacing(6)
        self.status_label = QLabel("● 待刷新")
        self.status_label.setProperty("status", "idle")
        self.status_label.setFixedWidth(190)
        right.addWidget(self.status_label)

        btn_row1 = QHBoxLayout()
        btn_row1.setSpacing(6)
        if self.on_move is not None:
            b = QPushButton("↑")
            b.setObjectName("cardBtn")
            b.setFixedSize(30, 26)
            b.setToolTip("上移")
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda: self._do_move(-1))
            btn_row1.addWidget(b)
        for text, handler in [("刷新", self._do_refresh), ("展示", self._do_show)]:
            b = QPushButton(text)
            b.setObjectName("cardBtn")
            b.setFixedSize(52, 26)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(handler)
            btn_row1.addWidget(b)
        right.addLayout(btn_row1)

        btn_row2 = QHBoxLayout()
        btn_row2.setSpacing(6)
        if self.on_move is not None:
            b = QPushButton("↓")
            b.setObjectName("cardBtn")
            b.setFixedSize(30, 26)
            b.setToolTip("下移")
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda: self._do_move(1))
            btn_row2.addWidget(b)
        for text, handler in [("编辑", self._do_edit), ("删除", self._do_delete)]:
            b = QPushButton(text)
            b.setObjectName("cardBtn")
            b.setFixedSize(52, 26)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(handler)
            btn_row2.addWidget(b)
        right.addLayout(btn_row2)
        root.addLayout(right, 0)

        self.set_busy(False)
        self._setup_type_link()

    def _provider_name(self) -> str:
        from .providers import get_provider_class
        cls = get_provider_class(self.entry.get("provider_id", ""))
        return cls.name if cls else "未知类型"

    @staticmethod
    def _elide(label: QLabel, text: str, width: int):
        """超长文本显示省略号，保持固定宽度对齐。"""
        fm = QFontMetrics(label.font())
        label.setText(fm.elidedText(text, Qt.TextElideMode.ElideRight, width))

    def _setup_type_link(self):
        """把类型名渲染成可点击链接（跳转到对应网站）。"""
        from .providers import get_provider_class
        cls = get_provider_class(self.entry.get("provider_id", ""))
        name = cls.name if cls else "未知类型"
        url = ""
        if cls is not None:
            url = cls.get_website_url(self.entry.get("config") or {})
        fm = QFontMetrics(self.type_label.font())
        shown = fm.elidedText(name, Qt.TextElideMode.ElideRight, 150)
        if url:
            self.type_label.setText(f'<a href="{url}" style="color:#4d6bfe;text-decoration:none;">{shown}</a>')
        else:
            self.type_label.setText(shown)

    def _open_site(self, url: str):
        QDesktopServices.openUrl(QUrl(url))

    def _set_status(self, key: str, text: str, tooltip: str = ""):
        """设置状态文字（限宽省略号，完整信息放 tooltip），颜色由主题 QSS 控制。"""
        fm = QFontMetrics(self.status_label.font())
        shown = fm.elidedText(text, Qt.TextElideMode.ElideRight, self.status_label.width() - 4)
        self.status_label.setProperty("status", key)
        self.status_label.setText(shown)
        if tooltip:
            self.status_label.setToolTip(tooltip)
        elif shown != text:
            self.status_label.setToolTip(text)
        else:
            self.status_label.setToolTip("")
        # 让属性变化立即反映到样式
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)

    def set_busy(self, busy: bool):
        if busy:
            self._set_status("busy", "● 刷新中…")
        else:
            self._set_status("idle", "● 待刷新")

    def set_result(self, info: QuotaInfo):
        if info.ok:
            self._set_status("ok", "● 正常")
        else:
            self._set_status("err", f"● 失败：{info.message}", info.message)

        # 余额：优先显示剩余，缺失时退回总额
        val = info.remaining if info.remaining is not None else info.total
        self.balance_label.setText(fmt_money(val, info.currency or ""))

    def _do_refresh(self):
        self.on_refresh(self.entry)

    def _do_show(self):
        if self.on_show is not None:
            self.on_show(self.entry)

    def _do_edit(self):
        self.on_edit(self.entry)

    def _do_delete(self):
        self.on_delete(self.entry)

    def _do_move(self, delta: int):
        if self.on_move is not None:
            self.on_move(self.uid, delta)


class SiteDialog(QDialog):
    """新增 / 编辑站点对话框：根据 Provider 的 config_schema 动态生成表单。"""

    def __init__(self, entry: dict | None = None, parent=None):
        super().__init__(parent)
        self.entry = entry
        self.setWindowTitle("编辑站点" if entry else "添加站点")
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setSpacing(10)

        self.display_name_edit = QLineEdit(entry.get("display_name", "") if entry else "")
        self.display_name_edit.setPlaceholderText("例如：我的中转站（仅界面显示用）")
        form.addRow("显示名称", self.display_name_edit)

        # 站点类型：新增时可选，编辑时锁定
        self.type_combo = QComboBox()
        self.provider_classes: list[type[Provider]] = list_provider_classes()
        for cls in self.provider_classes:
            self.type_combo.addItem(f"{cls.name}（{cls.id}）", cls.id)
        if entry:
            idx = self.type_combo.findData(entry.get("provider_id"))
            if idx >= 0:
                self.type_combo.setCurrentIndex(idx)
            self.type_combo.setEnabled(False)
            self.type_combo.setToolTip("站点类型创建后不可更改，请删除后重新添加。")
        form.addRow("站点类型", self.type_combo)

        self.type_combo.currentIndexChanged.connect(self._rebuild_fields)

        # 代理（可选）：所有站点类型通用的字段
        self.proxy_edit = QLineEdit()
        self.proxy_edit.setPlaceholderText("可选。访问国外站点需代理时填写，如 http://127.0.0.1:7890")
        form.addRow("代理（可选）", self.proxy_edit)

        layout.addLayout(form)

        self.fields_box = QVBoxLayout()
        layout.addLayout(self.fields_box)
        self.field_widgets: dict[str, QWidget] = {}

        # 自动刷新间隔（默认 3 分钟）
        auto = QHBoxLayout()
        self.auto_min = QSpinBox()
        self.auto_min.setRange(0, 1440)
        self.auto_min.setValue(3)
        self.auto_min.setSuffix(" 分钟（0=关闭）")
        auto.addWidget(QLabel("自动刷新间隔"))
        auto.addWidget(self.auto_min)
        layout.addLayout(auto)

        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.test_btn = self.buttons.addButton("测试连接", QDialogButtonBox.ButtonRole.ActionRole)
        self.test_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.test_btn.clicked.connect(self._test_connection)
        self.buttons.accepted.connect(self._on_ok)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

        self._rebuild_fields()
        if entry:
            self.auto_min.setValue(int(entry.get("auto_refresh_minutes", 0) or 0))
            self._load_values()

    def _current_provider_class(self) -> type[Provider]:
        cls_id = self.type_combo.currentData()
        for cls in self.provider_classes:
            if cls.id == cls_id:
                return cls
        return self.provider_classes[0]

    def _rebuild_fields(self):
        # 清空旧字段（含子布局，否则切换站点类型时旧输入框会残留）
        while self.fields_box.count():
            item = self.fields_box.takeAt(0)
            if item is None:
                continue
            w = item.widget()
            if w is not None:
                w.deleteLater()
            sub = item.layout()
            if sub is not None:
                while sub.count():
                    li = sub.takeAt(0)
                    sw = li.widget() if li else None
                    if sw is not None:
                        sw.deleteLater()
                sub.deleteLater()
        self.field_widgets.clear()

        cls = self._current_provider_class()
        for field in cls.config_schema:
            key = field["key"]
            label = field.get("label", key)
            ftype = field.get("type", TEXT)
            if ftype == NUMBER:
                w = QSpinBox()
                w.setRange(-10 ** 9, 10 ** 9)
                w.setValue(int(field.get("default", 0) or 0))
            else:
                w = QLineEdit()
                w.setPlaceholderText(field.get("placeholder", ""))
                if ftype == PASSWORD:
                    w.setEchoMode(QLineEdit.EchoMode.Password)
            self.field_widgets[key] = w
            row = QHBoxLayout()
            row.addWidget(w)
            cap = QLabel(label)
            cap.setMinimumWidth(90)
            self.fields_box.addWidget(cap)  # 直接加 label 作为说明
            self.fields_box.addLayout(row)

        desc = self._current_provider_class().description
        if desc:
            tip = QLabel(desc)
            tip.setWordWrap(True)
            tip.setProperty("role", "hint")
            self.fields_box.addWidget(tip)

    def _load_values(self):
        cfg = self.entry.get("config") or {}
        for key, w in self.field_widgets.items():
            v = cfg.get(key)
            if v is None:
                continue
            if isinstance(w, QLineEdit):
                w.setText(str(v))
            elif isinstance(w, QSpinBox):
                try:
                    w.setValue(int(v))
                except (TypeError, ValueError):
                    pass
        proxy = cfg.get("proxy")
        if proxy:
            self.proxy_edit.setText(str(proxy))

    def _build_entry(self) -> dict | None:
        """根据当前表单构建站点 entry；必填校验失败返回 None（已弹窗提示）。"""
        name = self.display_name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "提示", "请填写显示名称。")
            return None
        provider_id = self.type_combo.currentData()
        cls = self._current_provider_class()
        cfg = {}
        for field in cls.config_schema:
            key = field["key"]
            w = self.field_widgets.get(key)
            if w is None:
                continue
            if isinstance(w, QLineEdit):
                val = w.text().strip()
            else:
                val = w.value()
            if field.get("required") and not val:
                QMessageBox.warning(self, "提示", f"请填写「{field.get('label', key)}」。")
                return None
            if val != "":
                cfg[key] = val
        proxy = self.proxy_edit.text().strip()
        if proxy:
            cfg["proxy"] = proxy
        return {
            "uid": (self.entry or {}).get("uid") or f"p-{uuid.uuid4().hex[:8]}",
            "provider_id": provider_id,
            "display_name": name,
            "enabled": True,
            "auto_refresh_minutes": self.auto_min.value(),
            "config": cfg,
        }

    def _on_ok(self):
        entry = self._build_entry()
        if entry is None:
            return
        self.result_entry = entry
        self.accept()

    def _test_connection(self):
        """用当前表单里的配置异步测试一次连接。"""
        entry = self._build_entry()
        if entry is None:
            return
        self.test_btn.setEnabled(False)
        self.test_btn.setText("测试中…")
        # 信号桥不挂对话框父对象：对话框提前关闭时任务结果被安全丢弃
        bridge = TestBridge()
        bridge.done.connect(self._on_test_done)
        QThreadPool.globalInstance().start(TestTask(entry, bridge))

    def _on_test_done(self, info: QuotaInfo):
        self.test_btn.setEnabled(True)
        self.test_btn.setText("测试连接")
        if info.ok:
            QMessageBox.information(
                self, "连接成功",
                f"「{info.display_name}」查询正常！\n\n"
                f"剩余：{fmt_money(info.remaining, info.currency)}\n"
                f"总额：{fmt_money(info.total, info.currency)}\n"
                f"耗时：{getattr(info, '_elapsed', 0)}s",
            )
        else:
            QMessageBox.warning(self, "连接失败", f"「{info.display_name}」\n{info.message}")


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("API额度监控器")
        self.resize(860, 600)

        self.config = load_config()
        self.refresher = Refresher(self)
        self.refresher.finished.connect(self._on_finished)
        self.cards: dict[str, SiteCard] = {}
        self._results: dict[str, QuotaInfo] = {}  # uid -> 最近一次查询结果（排序重建时恢复显示）
        self.last_refresh: dict[str, float] = {}  # uid -> 最近一次刷新时间戳
        self._batch_id = 0                        # 批次号，用于隔离“全部刷新”统计
        self._batch: dict | None = None

        self._build_ui()
        self._setup_theme()
        self._restore_geometry()
        self._apply_config()
        self._rebuild_cards()

        # 自动刷新：每 30 秒轮询一次，逐个刷新到期的站点
        # （每个站点可单独设置间隔；没设置的用全局间隔兜底；都为 0 则不开自动刷新）
        self.auto_timer = QTimer(self)
        self.auto_timer.timeout.connect(self._auto_tick)
        self.auto_timer.start(30_000)
        self._show_auto_status()

        # 启动后自动刷新一次（有站点时）
        QTimer.singleShot(900, self._startup_refresh)

        self.statusBar().showMessage("就绪。点击「全部刷新」开始查询各站点额度。")

    # ============ 主题 ============
    def _setup_theme(self):
        """应用配置的主题、勾选菜单，并监听系统主题变化（跟随系统时自动切换）。"""
        app = QApplication.instance()
        apply_theme(app, self.config.theme)
        for act in self.theme_group.actions():
            act.setChecked(act.data() == self.config.theme)
        app.styleHints().colorSchemeChanged.connect(self._on_system_theme_changed)

    def _on_system_theme_changed(self, *_):
        if self.config.theme == "system":
            apply_theme(QApplication.instance(), "system")

    def _on_theme_clicked(self):
        act = self.theme_group.checkedAction()
        if act is None:
            return
        self.config.set_theme(act.data())
        self.config.save()
        apply_theme(QApplication.instance(), self.config.theme)
        self.statusBar().showMessage(f"主题已切换为：{act.text()}")

    # ============ UI 构建 ============
    def _restore_geometry(self):
        """恢复上次退出时的窗口位置和大小。"""
        geo = self.config.data.get("window_geometry")
        if geo:
            try:
                self.restoreGeometry(QByteArray.fromBase64(geo.encode("ascii")))
            except Exception:  # noqa: BLE001 —— 损坏的几何数据直接忽略
                pass

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(12, 10, 12, 8)
        root.setSpacing(10)

        # —— 菜单栏：设置（主题）+ 帮助 ——
        settings_menu = self.menuBar().addMenu("设置")
        theme_menu = settings_menu.addMenu("主题")
        self.theme_group = QActionGroup(self)
        for key, label in [("light", "浅色"), ("dark", "深色"), ("system", "跟随系统")]:
            act = theme_menu.addAction(label)
            act.setCheckable(True)
            act.setData(key)
            self.theme_group.addAction(act)
            act.triggered.connect(self._on_theme_clicked)

        help_menu = self.menuBar().addMenu("帮助")
        help_action = help_menu.addAction("使用说明")
        help_action.triggered.connect(self._show_help)
        about_action = help_menu.addAction("关于")
        about_action.triggered.connect(self._show_about)
        open_cfg_action = help_menu.addAction("打开配置文件")
        open_cfg_action.triggered.connect(self._open_config_file)

        # —— 顶部工具栏（标题 + 小字竖排；控件两行、宽度统一） ——
        # 第一行：标题（含下方小字）| 搜索框
        bar1 = QHBoxLayout()
        bar1.setSpacing(8)

        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        title = QLabel("📊 API额度监控器")
        title.setProperty("role", "apptitle")
        title_box.addWidget(title)
        subtitle = QLabel("默认自动刷新时间 3 分钟")
        subtitle.setProperty("role", "appsubtitle")
        title_box.addWidget(subtitle)
        bar1.addLayout(title_box)
        bar1.addStretch(1)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("🔍 搜索站点…")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.textChanged.connect(self._apply_filter)
        bar1.addWidget(self.search_edit)

        # 第二行：全部刷新 | 添加站点（靠右）
        bar2 = QHBoxLayout()
        bar2.setSpacing(8)
        bar2.addStretch(1)

        self.refresh_all_btn = QPushButton("全部刷新")
        self.refresh_all_btn.setObjectName("primaryBtn")
        self.refresh_all_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.refresh_all_btn.clicked.connect(self._refresh_all)
        bar2.addWidget(self.refresh_all_btn)

        add_btn = QPushButton("添加站点")
        add_btn.setObjectName("primaryBtn")
        add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_btn.clicked.connect(self._add_site)
        bar2.addWidget(add_btn)

        # 按钮文字调小一点，保证完整显示
        for b in (self.refresh_all_btn, add_btn):
            b.setStyleSheet("font-size: 12px;")
        self.refresh_all_btn.ensurePolished()
        add_btn.ensurePolished()

        # 两个按钮统一宽度 = 两者中更宽的那个（避免“添加站点”被截断）
        common_w = max(self.refresh_all_btn.sizeHint().width(),
                       add_btn.sizeHint().width())
        for wgt in (self.refresh_all_btn, add_btn):
            wgt.setFixedWidth(common_w)
        # 搜索框横跨两个按钮的宽度（左对齐全部刷新左边、右对齐添加站点右边）
        self.search_edit.setFixedWidth(common_w * 2 + 8)

        root.addLayout(bar1)
        root.addLayout(bar2)

        # —— 滚动区域：站点卡片 ——
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.cards_host = QWidget()
        self.cards_layout = QVBoxLayout(self.cards_host)
        self.cards_layout.setContentsMargins(2, 2, 2, 2)
        self.cards_layout.setSpacing(10)
        self.cards_layout.addStretch(1)
        scroll.setWidget(self.cards_host)
        root.addWidget(scroll, 1)

    def _empty_hint(self):
        """没有站点时显示引导文案。"""
        hint = QLabel("还没有配置任何站点。\n点击右上角「＋ 添加站点」，把每个网站的接口地址、Key 等信息填进去。")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setProperty("role", "hint")
        hint.setStyleSheet("padding: 40px;")
        self.cards_layout.addWidget(hint)

    def _open_config_file(self):
        """用系统默认编辑器打开 config.json（或打开所在文件夹）。"""
        import os
        from .config import config_path
        path = config_path()
        try:
            if os.path.exists(path):
                os.startfile(path)  # Windows：默认程序打开
            else:
                # 文件还没生成，打开所在目录
                os.startfile(os.path.dirname(path))
        except OSError as e:
            QMessageBox.warning(self, "提示", f"无法打开配置文件：{e}\n\n文件位置：{path}")

    def _show_about(self):
        from .version import APP_NAME, VERSION
        QMessageBox.information(
            self, "关于",
            f"{APP_NAME}\n"
            f"版本：v{VERSION}\n\n"
            f"功能：集中查看各网站大模型 API 的剩余额度\n\n"
            f"支持窗口置顶、深色主题、搜索排序、单站点展示窗。",
        )

    def _show_help(self):
        QMessageBox.information(
            self, "使用说明",
            "【添加站点】\n"
            "点击右上角「＋ 添加站点」，选择站点类型（如 OpenAI 兼容计费接口、\n"
            "One-API/New-API 框架），按提示填写接口地址、Key 等信息，\n"
            "可先点「测试连接」确认配置无误。\n\n"
            "【窗口置顶】\n"
            "工具栏「📌 窗口置顶」按钮，一键让窗口始终显示在最前面，\n"
            "适合边看额度边在浏览器操作。\n\n"
            "【自动刷新】\n"
            "每个站点可单独设置自动刷新间隔（分钟，0=关闭）。\n"
            "也可直接编辑 exe 同目录的 config.json 里的 auto_refresh_minutes\n"
            "作为全局兜底间隔。\n\n"
            "【需要新网站适配】\n"
            "本程序采用适配器架构，每个网站一个适配器。\n"
            "想接入新网站时，把该网站查额度的接口地址、返回的 JSON 示例、\n"
            "额度字段含义告诉开发者即可添加。\n\n"
            "【配置文件】\n"
            "站点配置保存在 exe 同目录的 config.json，可直接编辑、备份。",
        )

    # ============ 状态应用 ============
    def _apply_config(self):
        # 置顶状态仍由 config 驱动（无 UI 按钮，可在 config.json 里设置）
        self._set_topmost(self.config.always_on_top)

    def _set_topmost(self, on: bool):
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, on)
        self.show()

    # ============ 站点卡片管理 ============
    def _rebuild_cards(self):
        # 清空
        while self.cards_layout.count():
            item = self.cards_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        self.cards.clear()
        self.no_match_label = None

        entries = self.config.providers()
        if not entries:
            self._empty_hint()
            return

        # “没有匹配的站点”提示（搜索过滤后全隐藏时显示）
        self.no_match_label = QLabel("没有匹配的站点")
        self.no_match_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.no_match_label.setProperty("role", "hint")
        self.no_match_label.setStyleSheet("padding: 30px;")
        self.no_match_label.hide()
        self.cards_layout.insertWidget(self.cards_layout.count() - 1, self.no_match_label)

        for entry in entries:
            uid = entry.get("uid") or entry.get("provider_id", "")
            card = SiteCard(entry, self._refresh_one, self._edit_site, self._delete_site,
                            on_move=self._move_card, on_show=self._show_site)
            self.cards_layout.insertWidget(self.cards_layout.count() - 1, card)
            self.cards[uid] = card
            # 恢复该站点最近一次查询结果（排序/重建后余额不丢失）
            prev = self._results.get(uid)
            if prev is not None:
                card.set_result(prev)

        # 尾部弹性空间：吸收多余高度，保证卡片始终保持自然高度
        # （否则搜索隐藏部分卡片后，剩余卡片会被拉伸占满窗口）
        self.cards_layout.addStretch(1)

        self._apply_filter()  # 重建后重新应用搜索过滤

    def _apply_filter(self, *_):
        """按显示名/类型名过滤卡片。"""
        query = self.search_edit.text().strip().lower()
        visible = 0
        for card in self.cards.values():
            name = (card.entry.get("display_name") or "").lower()
            pname = (card._provider_name() or "").lower()
            match = (not query) or (query in name) or (query in pname)
            card.setVisible(match)
            if match:
                visible += 1
        if self.no_match_label is not None:
            self.no_match_label.setVisible(bool(query) and visible == 0)

    def _move_card(self, uid: str, delta: int):
        """上下移动卡片顺序（同时持久化到 config.json）。"""
        providers = self.config.providers()
        idx = None
        for i, p in enumerate(providers):
            if (p.get("uid") or p.get("provider_id", "")) == uid:
                idx = i
                break
        if idx is None:
            return
        new_idx = idx + delta
        if new_idx < 0 or new_idx >= len(providers):
            return
        providers[idx], providers[new_idx] = providers[new_idx], providers[idx]
        self.config.save()
        self._rebuild_cards()

    # ============ 展示窗口 ============
    def _show_site(self, entry: dict):
        """打开展示窗口并隐藏主窗口；返回时恢复。"""
        from .show_window import ShowWindow
        uid = entry.get("uid") or entry.get("provider_id", "")
        info = self._results.get(uid)
        # 读取上次记住的展示窗口大小（由主窗口统一管理，避免写冲突）
        size = self.config.data.get("show_window_size")
        initial_size = None
        if size:
            try:
                initial_size = (int(size.get("w", 0)), int(size.get("h", 0)))
            except (TypeError, ValueError):
                initial_size = None
        self._show_win = ShowWindow(entry, info, on_close=self._restore_main_window,
                                    initial_size=initial_size)
        # 先定位到主窗口中心（保证在当前屏幕可见，不会跑到屏幕外），再显示
        if self.isVisible() and self.frameGeometry().isValid():
            self._show_win.move(self.frameGeometry().center() - self._show_win.rect().center())
        self._show_win.show()
        self._show_win.raise_()
        self._show_win.activateWindow()
        self.hide()

    def _restore_main_window(self, size=None):
        """展示窗口关闭后恢复主窗口，并保存展示窗口的大小。"""
        if size:
            self.config.data["show_window_size"] = {"w": size[0], "h": size[1]}
            self.config.save()
        win = getattr(self, "_show_win", None)
        if win is not None:
            win.deleteLater()
            self._show_win = None
        self.show()
        self.raise_()
        self.activateWindow()

    def _add_site(self):
        dlg = SiteDialog(parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.config.upsert_provider(dlg.result_entry)
            self.config.save()
            self._rebuild_cards()
            self._refresh_one(dlg.result_entry)

    def _edit_site(self, entry: dict):
        dlg = SiteDialog(entry, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            uid = dlg.result_entry.get("uid")
            self._results.pop(uid, None)  # 配置已变，旧结果作废
            self.config.upsert_provider(dlg.result_entry)
            self.config.save()
            self._rebuild_cards()
            self._restart_auto_timer()
            # 保存后立即用新配置刷新一次，覆盖编辑前可能还在跑的旧任务结果
            self._refresh_one(dlg.result_entry)

    def _delete_site(self, entry: dict):
        uid = entry.get("uid") or entry.get("provider_id", "")
        ret = QMessageBox.question(
            self, "确认删除",
            f"确定删除站点「{entry.get('display_name')}」？\n（配置会被移除，不会影响网站上的账户）",
        )
        if ret == QMessageBox.StandardButton.Yes:
            self.config.remove_provider(uid)
            self._results.pop(uid, None)
            self.config.save()
            self._rebuild_cards()

    # ============ 刷新 ============
    def _enabled_entries(self) -> list[dict]:
        return [e for e in self.config.providers() if e.get("enabled", True)]

    def _startup_refresh(self):
        """启动后自动刷新一次（无站点时静默提示，不弹窗）。"""
        if not self._enabled_entries():
            self.statusBar().showMessage("启动完成。点击「＋ 添加站点」配置第一个网站。")
            return
        self._refresh_all()

    def _refresh_all(self):
        entries = self._enabled_entries()
        if not entries:
            QMessageBox.information(self, "提示", "没有可刷新的站点，请先「添加站点」。")
            return
        # 只把本次实际提交的站点卡片置为“刷新中”（避免禁用站点永久卡住）
        for e in entries:
            card = self.cards.get(e.get("uid"))
            if card:
                card.set_busy(True)
        self._batch_id += 1
        self.refresher.refresh_all(entries, batch_id=self._batch_id)
        # 批次汇总统计：batch_id 隔离，旧批次结果不参与统计
        self._batch = {"id": self._batch_id,
                       "uids": {e.get("uid") or e.get("provider_id", "") for e in entries},
                       "ok": 0, "fail": 0}
        self.statusBar().showMessage(f"正在刷新 {len(entries)} 个站点…")

    def _refresh_one(self, entry: dict):
        uid = entry.get("uid") or entry.get("provider_id", "")
        card = self.cards.get(uid)
        if card:
            card.set_busy(True)
        self.refresher.refresh_one(entry)

    def _on_finished(self, batch_id: str, uid: str, info: QuotaInfo):
        card = self.cards.get(uid)
        if card:
            card.set_result(info)
        if uid:
            self._results[uid] = info  # 缓存结果，排序重建时恢复显示
            self.last_refresh[uid] = time.time()
        elapsed = getattr(info, "_elapsed", 0)
        if info.ok:
            self.statusBar().showMessage(
                f"「{info.display_name}」刷新完成，剩余 {fmt_money(info.remaining, info.currency)}（{elapsed}s）"
            )
        else:
            self.statusBar().showMessage(f"「{info.display_name}」刷新失败：{info.message}")
        # 批次统计：只统计当前批次（batch_id 匹配）的结果，旧批次任务不参与
        batch = getattr(self, "_batch", None)
        if batch and batch_id and batch_id == batch["id"] and uid in batch["uids"]:
            batch["uids"].discard(uid)
            if info.ok:
                batch["ok"] += 1
            else:
                batch["fail"] += 1
            total = batch["ok"] + batch["fail"]
            if not batch["uids"]:
                self.statusBar().showMessage(
                    f"刷新完成：{batch['ok']} 个正常 / {batch['fail']} 个失败（共 {total} 个站点）"
                )
                self._batch = None
            else:
                self.statusBar().showMessage(f"正在刷新：{total}/{total + len(batch['uids'])} …")

    # ============ 自动刷新 ============
    def _any_auto_enabled(self) -> bool:
        if self.config.auto_refresh_minutes > 0:
            return True
        return any(int(e.get("auto_refresh_minutes", 0) or 0) > 0 for e in self.config.providers())

    def _show_auto_status(self):
        if self._any_auto_enabled():
            self.statusBar().showMessage("自动刷新已开启：每个站点按各自设置的间隔自动刷新。")
        else:
            self.statusBar().showMessage("就绪。点击「全部刷新」开始查询各站点额度。")

    def _restart_auto_timer(self):
        # 站点配置变化后刷新提示信息（轮询定时器常驻，无需重启）
        self._show_auto_status()

    def _auto_tick(self):
        now = time.time()
        for entry in self._enabled_entries():
            uid = entry.get("uid") or entry.get("provider_id", "")
            interval = int(entry.get("auto_refresh_minutes", 0) or 0)
            if interval <= 0:
                interval = self.config.auto_refresh_minutes
            if interval <= 0:
                continue
            if now - self.last_refresh.get(uid, 0) >= interval * 60:
                self._refresh_one(entry)

    def closeEvent(self, event):
        # 记忆窗口位置和大小
        geo = bytes(self.saveGeometry().toBase64()).decode()
        self.config.data["window_geometry"] = geo
        self.config.save()
        # 丢弃排队中的刷新任务，并限时等待正在执行的任务结束（避免退出时强杀请求）
        try:
            self.refresher.pool.clear()
            self.refresher.pool.waitForDone(1500)
        except Exception:  # noqa: BLE001 —— 退出流程不因等待失败而卡住
            pass
        super().closeEvent(event)
