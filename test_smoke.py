"""无界面自检：不依赖真实 API Key，用本地假服务器验证核心逻辑。

运行：python test_smoke.py
"""
import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

# 保证能 import app 包
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


# ---------- 假服务器：模拟 OpenAI 兼容 + One-API 计费接口 ----------
class FakeOpenAI(BaseHTTPRequestHandler):
    def do_GET(self):
        if "/error-test" in self.path:
            body = json.dumps({"error": {"message": "boom", "type": "server_error"}}).encode()
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)
        elif self.path.endswith("/v1/dashboard/billing/credit_grants"):
            body = json.dumps({
                "object": "credit_grants",
                "total_granted": 18.0,
                "total_used": 10.5,
                "total_available": 7.5,
                "grants": {"data": [{"expires_at": "2025-12-31T00:00:00Z"}]},
            }).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)
        elif self.path.endswith("/api/user/self"):
            body = json.dumps({
                "success": True,
                "message": "",
                "data": {"id": 1, "username": "tester",
                         "quota": 4981234, "used_quota": 18766, "request_count": 123},
            }).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)
        elif self.path.endswith("/user/balance"):
            body = json.dumps({
                "is_available": True,
                "balance_infos": [{
                    "currency": "CNY",
                    "total_balance": "16.71",
                    "granted_balance": "0.00",
                    "topped_up_balance": "16.71",
                }],
            }).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *a):
        pass


class FakeRetry(FakeOpenAI):
    """模拟网络抖动：第一次请求直接断开连接，第二次正常返回。"""

    count = 0

    def do_GET(self):
        if "/retry-test" in self.path:
            FakeRetry.count += 1
            if FakeRetry.count == 1:
                self.connection.close()  # 客户端收到连接重置 -> 触发重试
                return
            body = json.dumps({
                "object": "credit_grants",
                "total_granted": 10.0,
                "total_used": 2.0,
                "total_available": 8.0,
                "grants": {"data": []},
            }).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)
        else:
            super().do_GET()

    def log_message(self, *a):
        pass


class FakeMax66(BaseHTTPRequestHandler):
    """模拟 max66.xyz：POST /user/login + GET /user/dashboard。"""

    def _send(self, code, body: bytes, ctype="application/json"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path.endswith("/user/login"):
            body = json.dumps({
                "ok": True, "api_key": "sk-test", "email_verified": True,
                "remaining_calls": 0, "paygo_balance": 4.105059004000015,
                "verify_hint": "",
            }).encode()
            self._send(200, body)
        else:
            self._send(404, b'{"detail":"Not Found"}')

    def do_GET(self):
        if self.path.endswith("/user/dashboard"):
            html = ('<div class="stats">'
                    '<div class="stat"><div class="v">0</div><div class="l">剩余次数</div></div>'
                    '<div class="stat"><div class="v">¥4.11</div><div class="l">按量余额</div></div>'
                    '<div class="stat"><div class="v">0</div><div class="l">今日已用</div></div>'
                    '</div>').encode()
            self._send(200, html, "text/html; charset=utf-8")
        else:
            self._send(404, b'{"detail":"Not Found"}')

    def log_message(self, *a):
        pass


def start_fake_server(handler=FakeOpenAI) -> HTTPServer:
    srv = HTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


# ---------- 自检 ----------
passed = 0
failed = 0


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"  [PASS] {name}")
    else:
        failed += 1
        print(f"  [FAIL] {name}  {detail}")


def test_config():
    print("== 配置读写 ==")
    from app.config import Config
    c = Config()
    c.set_always_on_top(True)
    c.upsert_provider({"uid": "p-test", "provider_id": "openai_compat", "display_name": "测试站", "config": {"base_url": "http://x", "api_key": "k"}})
    check("置顶标志可设置", c.always_on_top is True)
    check("站点 upsert", c.provider_by_uid("p-test") is not None)
    c.remove_provider("p-test")
    check("站点删除", c.provider_by_uid("p-test") is None)


def test_config_corrupt():
    print("== config.json 损坏恢复 ==")
    import app.config as cfgmod
    path = cfgmod.config_path()
    # 1. 损坏 JSON
    with open(path, "w", encoding="utf-8") as f:
        f.write("{ not valid json")
    c = cfgmod.load_config()
    check("损坏 JSON 不崩溃", c.providers() == [])
    check("损坏文件被备份", os.path.exists(path + ".bak"))
    # 2. providers 类型错误（list 顶层 / dict providers）
    with open(path, "w", encoding="utf-8") as f:
        f.write('["not", "a", "dict"]')
    c2 = cfgmod.load_config()
    check("顶层非对象不崩溃", c2.providers() == [])
    with open(path, "w", encoding="utf-8") as f:
        f.write('{"providers": {"a": 1}, "always_on_top": false}')
    c3 = cfgmod.load_config()
    check("providers 类型错误不崩溃", c3.providers() == [])
    # 3. 清理
    for p in (path, path + ".bak"):
        if os.path.exists(p):
            os.remove(p)


def test_registry():
    print("== 适配器注册表 ==")
    from app.providers import get_provider_class, list_provider_classes
    cls = get_provider_class("openai_compat")
    check("openai_compat 已注册", cls is not None)
    check("注册表非空", len(list_provider_classes()) >= 1)


def test_provider_parse():
    print("== OpenAI 兼容适配器解析 ==")
    from app.providers.openai_compat import OpenAICompatProvider
    srv = start_fake_server()
    port = srv.server_address[1]
    try:
        p = OpenAICompatProvider({"base_url": f"http://127.0.0.1:{port}", "api_key": "sk-test"})
        info = p.fetch(p._new_session(timeout=5))
        check("fetch 成功", info.ok, info.message)
        check("总额=18", info.total == 18.0, str(info.total))
        check("已用=10.5", info.used == 10.5, str(info.used))
        check("剩余=7.5", info.remaining == 7.5, str(info.remaining))
        check("过期时间", "2025-12-31" in info.expires_at, info.expires_at)
    finally:
        srv.shutdown()

    # 缺 key 应报错
    p2 = OpenAICompatProvider({"base_url": "http://x"})
    try:
        p2.fetch(p2._new_session(timeout=5))
        check("缺 key 应抛错", False)
    except Exception as e:
        check("缺 key 抛错", "API Key" in str(e), str(e))


def test_oneapi_parse():
    print("== One-API/New-API 适配器解析 ==")
    from app.providers.oneapi_newapi import OneApiProvider
    srv = start_fake_server()
    port = srv.server_address[1]
    try:
        p = OneApiProvider({"base_url": f"http://127.0.0.1:{port}",
                            "access_token": "sk-token", "quota_per_dollar": 500000})
        info = p.fetch(p._new_session(timeout=5))
        check("fetch 成功", info.ok, info.message)
        # 4981234 / 500000 = 9.962468 ; 18766 / 500000 = 0.037532
        check("剩余≈9.9625", abs(info.remaining - 9.962468) < 1e-6, str(info.remaining))
        check("已用≈0.0375", abs(info.used - 0.037532) < 1e-6, str(info.used))
        check("总额≈10.0", abs(info.total - 10.0) < 1e-6, str(info.total))
        check("币种默认 CNY", info.currency == "CNY")
    finally:
        srv.shutdown()

    # 换算比例可配置（如 1 美元 = 100000 内部额度）
    p2 = OneApiProvider({"base_url": "http://127.0.0.1:1", "access_token": "x",
                         "quota_per_dollar": 100000})
    ratio = p2._num(p2.cfg("quota_per_dollar"))
    check("比例字段可读取", ratio == 100000, str(ratio))

    # 缺少 token 应报错
    p3 = OneApiProvider({"base_url": "http://x"})
    try:
        p3.fetch(p3._new_session(timeout=5))
        check("缺 token 应抛错", False)
    except Exception as e:
        check("缺 token 抛错", "Access Token" in str(e), str(e))


def test_pin_flag():
    print("== 窗口置顶逻辑（offscreen）==")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import Qt, QEventLoop, QTimer
    from PySide6.QtWidgets import QApplication
    from app.main_window import MainWindow

    app = QApplication.instance() or QApplication([])
    w = MainWindow()
    check("默认不置顶", not (w.windowFlags() & Qt.WindowType.WindowStaysOnTopHint))
    w._set_topmost(True)
    check("置顶标志生效", bool(w.windowFlags() & Qt.WindowType.WindowStaysOnTopHint))
    w._set_topmost(False)
    check("取消后置顶标志移除", not (w.windowFlags() & Qt.WindowType.WindowStaysOnTopHint))

    # 启动自动刷新：无站点时应静默提示，不弹窗不崩溃
    loop = QEventLoop()
    QTimer.singleShot(1500, loop.quit)
    loop.exec()
    check("启动自动刷新（无站点静默）", "启动完成" in w.statusBar().currentMessage())

    w.close()
    # 清理测试产生的 config.json
    cfg = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
    if os.path.exists(cfg):
        os.remove(cfg)


def test_dialog_fields_rebuild():
    print("== 站点对话框字段重建 ==")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    from app.main_window import SiteDialog

    app = QApplication.instance() or QApplication([])
    dlg = SiteDialog(parent=None)
    # 初始：openai_compat 有 3 个字段（base_url, api_key, currency）
    check("初始字段数=3", len(dlg.field_widgets) == 3, str(len(dlg.field_widgets)))
    # 切换到 oneapi：4 个字段（含数字比例字段和币种）
    idx = dlg.type_combo.findData("oneapi_newapi")
    check("可切换 to oneapi", idx >= 0)
    dlg.type_combo.setCurrentIndex(idx)
    check("切换后字段数=4", len(dlg.field_widgets) == 4, str(len(dlg.field_widgets)))
    check("数字字段默认 500000", dlg.field_widgets["quota_per_dollar"].value() == 500000)
    # 再切回 openai：字段数应回到 3，且无残留
    idx2 = dlg.type_combo.findData("openai_compat")
    dlg.type_combo.setCurrentIndex(idx2)
    check("切回后字段数=3", len(dlg.field_widgets) == 3, str(len(dlg.field_widgets)))

    # 代理字段 + 表单构建
    check("有代理输入框", hasattr(dlg, "proxy_edit"))
    check("自动刷新默认 3 分钟", dlg.auto_min.value() == 3, str(dlg.auto_min.value()))
    dlg.proxy_edit.setText("http://127.0.0.1:7890")
    dlg.display_name_edit.setText("代理测试站")
    dlg.field_widgets["base_url"].setText("http://x.example")
    dlg.field_widgets["api_key"].setText("sk-test")
    entry = dlg._build_entry()
    check("代理保存进 config", entry and entry["config"].get("proxy") == "http://127.0.0.1:7890")
    check("测试连接按钮存在", hasattr(dlg, "test_btn"))

    dlg.deleteLater()


def test_deepseek_parse():
    print("== DeepSeek 官方适配器解析 ==")
    from app.providers.deepseek import DeepSeekProvider
    srv = start_fake_server()
    port = srv.server_address[1]
    # 用真实域名不适用，直接把 API_BASE 指向本地假服务器做单元验证
    import app.providers.deepseek as ds_mod
    old_base = ds_mod.API_BASE
    ds_mod.API_BASE = f"http://127.0.0.1:{port}"
    try:
        p = DeepSeekProvider({"api_key": "sk-test"})
        info = p.fetch(p._new_session(timeout=5))
        check("fetch 成功", info.ok, info.message)
        check("总额=16.71", info.total == 16.71, str(info.total))
        check("剩余=16.71", info.remaining == 16.71, str(info.remaining))
        check("币种 CNY", info.currency == "CNY")
        check("已用为 None", info.used is None)
        check("message 含赠送/充值", "赠送" in info.message and "充值" in info.message)
    finally:
        ds_mod.API_BASE = old_base
        srv.shutdown()

    # 缺 key 应报错
    try:
        DeepSeekProvider({"base_url": "http://x"}).fetch(DeepSeekProvider({})._new_session(timeout=5))
        check("缺 key 应抛错", False)
    except Exception as e:
        check("缺 key 抛错", "API Key" in str(e), str(e))


def test_max66_parse():
    print("== MaxAI 适配器解析 ==")
    from app.providers.max66 import Max66Provider
    import app.providers.max66 as m66
    srv = start_fake_server(FakeMax66)
    port = srv.server_address[1]
    old_login, old_dash = m66.LOGIN_URL, m66.DASH_URL
    m66.LOGIN_URL = f"http://127.0.0.1:{port}/user/login"
    m66.DASH_URL = f"http://127.0.0.1:{port}/user/dashboard"
    try:
        p = Max66Provider({"email": "a@b.com", "password": "secret"})
        info = p.fetch(p._new_session(timeout=5))
        check("fetch 成功", info.ok, info.message)
        check("按量余额≈4.105", info.remaining is not None and abs(info.remaining - 4.105059004000015) < 1e-9, str(info.remaining))
        check("币种 CNY", info.currency == "CNY")
        check("extra 含剩余次数", "剩余次数 0" in info.extra, info.extra)
        check("extra 含今日已用", "今日已用 0" in info.extra, info.extra)
    finally:
        m66.LOGIN_URL, m66.DASH_URL = old_login, old_dash
        srv.shutdown()

    # 缺密码应报错
    try:
        Max66Provider({"email": "a@b.com"}).fetch(Max66Provider({"email": "a"})._new_session(timeout=5))
        check("缺密码应抛错", False)
    except Exception as e:
        check("缺密码抛错", "密码" in str(e), str(e))


def test_fetch_entry_and_testtask():
    print("== fetch_entry / TestTask 机制 ==")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import QEventLoop, QThreadPool, QTimer
    from PySide6.QtWidgets import QApplication
    from app.worker import TestBridge, TestTask, fetch_entry

    app = QApplication.instance() or QApplication([])
    srv = start_fake_server()
    port = srv.server_address[1]
    try:
        entry = {"uid": "t1", "provider_id": "openai_compat", "display_name": "测试",
                 "config": {"base_url": f"http://127.0.0.1:{port}", "api_key": "sk-x"}}
        # fetch_entry 直接调用（含代理字段透传，代理本身不影响本地直连目标）
        info = fetch_entry(entry)
        check("fetch_entry 成功", info.ok, info.message)
        check("fetch_entry 剩余=7.5", info.remaining == 7.5, str(info.remaining))

        # TestTask 异步 + 信号回调
        result = {}
        loop = QEventLoop()
        bridge = TestBridge()
        bridge.done.connect(lambda i: (result.update(info=i), loop.quit()))
        QTimer.singleShot(5000, loop.quit)
        QThreadPool.globalInstance().start(TestTask(entry, bridge))
        loop.exec()
        check("TestTask 信号回调", "info" in result and result["info"].ok,
              result.get("info").message if result.get("info") else "无回调")
    finally:
        srv.shutdown()


def test_retry():
    print("== 网络错误自动重试 ==")
    from app.worker import fetch_entry
    srv = start_fake_server(FakeRetry)
    port = srv.server_address[1]
    try:
        FakeRetry.count = 0
        entry = {"uid": "r", "provider_id": "openai_compat", "display_name": "重试测试",
                 "config": {"base_url": f"http://127.0.0.1:{port}/retry-test", "api_key": "sk-x"}}
        info = fetch_entry(entry)
        check("重试后成功", info.ok, info.message)
        check("实际请求 2 次", FakeRetry.count == 2, str(FakeRetry.count))
        check("剩余=8.0", info.remaining == 8.0, str(info.remaining))
    finally:
        srv.shutdown()


def test_geometry():
    print("== 窗口几何记忆 ==")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    from app.main_window import MainWindow

    app = QApplication.instance() or QApplication([])
    w = MainWindow()
    w.resize(700, 500)
    geo = bytes(w.saveGeometry().toBase64()).decode()
    w.close()  # closeEvent 会把几何写入 config.json
    w2 = MainWindow()
    check("config 已保存几何", bool(w2.config.data.get("window_geometry")))
    check("几何数据与保存一致", w2.config.data.get("window_geometry") == geo)
    w2.close()
    # 清理测试产生的 config.json
    cfg = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
    if os.path.exists(cfg):
        os.remove(cfg)


def test_http_error_status():
    print("== HTTP 错误状态码处理 ==")
    from app.providers.openai_compat import OpenAICompatProvider
    srv = start_fake_server()
    port = srv.server_address[1]
    try:
        p = OpenAICompatProvider({"base_url": f"http://127.0.0.1:{port}/error-test", "api_key": "sk-x"})
        try:
            p.fetch(p._new_session(timeout=5))
            check("500 应抛错", False)
        except Exception as e:
            check("500 抛 ProviderError", "500" in str(e) and "boom" in str(e), str(e))
    finally:
        srv.shutdown()



def test_website_urls():
    print("== 站点跳转 URL ==")
    from app.providers import get_provider_class

    cases = [
        ("deepseek_official", {}, "https://platform.deepseek.com/usage"),
        ("max66_zhongzhuan", {}, "https://max66.xyz/user/dashboard"),
        ("openai_compat", {"base_url": "https://api.example.com"}, "https://api.example.com"),
        ("oneapi_newapi", {"base_url": "https://chat.example.com/"}, "https://chat.example.com"),
    ]
    for pid, cfg, expect in cases:
        cls = get_provider_class(pid)
        got = cls.get_website_url(cfg) if cls else ""
        check(f"{pid} URL", got == expect, f"{got!r} != {expect!r}")


def test_search_and_sort():
    print("== 搜索过滤 + 卡片排序 ==")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    from app.main_window import MainWindow

    app = QApplication.instance() or QApplication([])
    w = MainWindow()
    w.config.upsert_provider({"uid": "p-a", "provider_id": "deepseek_official",
                              "display_name": "DeepSeek 官方", "enabled": True,
                              "auto_refresh_minutes": 3, "config": {}})
    w.config.upsert_provider({"uid": "p-b", "provider_id": "max66_zhongzhuan",
                              "display_name": "MaxAI 中转站", "enabled": True,
                              "auto_refresh_minutes": 3, "config": {}})
    w._rebuild_cards()
    check("两个卡片已创建", len(w.cards) == 2, str(len(w.cards)))

    # —— 排序 ——
    w._move_card("p-b", -1)  # MaxAI 上移
    order = [p.get("uid") for p in w.config.providers()]
    check("上移后顺序正确", order == ["p-b", "p-a"], str(order))
    w._move_card("p-b", 1)   # MaxAI 下移回来
    order = [p.get("uid") for p in w.config.providers()]
    check("下移后顺序正确", order == ["p-a", "p-b"], str(order))
    w._move_card("p-a", -1)  # 第一个不能再上移（越界应忽略）
    order = [p.get("uid") for p in w.config.providers()]
    check("越界上移被忽略", order == ["p-a", "p-b"], str(order))

    # —— 排序后余额恢复 ——
    from app.providers.base import QuotaInfo
    w._on_finished("", "p-a", QuotaInfo(ok=True, provider_id="deepseek_official",
                                        display_name="DeepSeek 官方", remaining=16.68,
                                        total=16.68, currency="CNY", message="ok"))
    w._on_finished("", "p-b", QuotaInfo(ok=True, provider_id="max66_zhongzhuan",
                                        display_name="MaxAI 中转站", remaining=4.11,
                                        total=4.11, currency="CNY", message="ok"))
    check("余额已显示", "16.68" in w.cards["p-a"].balance_label.text())
    w._move_card("p-b", -1)  # 排序触发重建
    check("排序后余额仍显示", "16.68" in w.cards["p-a"].balance_label.text()
          and "4.11" in w.cards["p-b"].balance_label.text(),
          f"{w.cards['p-a'].balance_label.text()} / {w.cards['p-b'].balance_label.text()}")

    # —— 搜索过滤（且卡片高度不变） ——
    w.show()
    app.processEvents()
    h_before = w.cards["p-a"].height()
    check("卡片有实际高度", h_before > 50, str(h_before))
    w.search_edit.setText("deep")
    app.processEvents()
    h_after = w.cards["p-a"].height()
    check("搜索后卡片高度不变", h_after == h_before, f"{h_before} -> {h_after}")
    check("搜索 deep 命中", w.cards["p-a"].isVisible() and not w.cards["p-b"].isVisible())
    w.search_edit.setText("中转")
    check("搜索中文命中", not w.cards["p-a"].isVisible() and w.cards["p-b"].isVisible())
    w.search_edit.setText("不存在站")
    check("无匹配时提示显示", w.no_match_label is not None and w.no_match_label.isVisible())
    w.search_edit.setText("")
    check("清空搜索全部恢复", w.cards["p-a"].isVisible() and w.cards["p-b"].isVisible())

    w.close()
    # 清理测试产生的 config.json
    cfg = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
    if os.path.exists(cfg):
        os.remove(cfg)


def test_fonts():
    print("== 内置 Maple 字体加载 ==")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    import main as main_mod
    family = main_mod.load_app_fonts()
    check("字体加载成功", family is not None, str(family))
    if family:
        check("字体家族名", "Maple" in family, family)


def test_theme():
    print("== 主题切换 ==")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    from app.config import Config
    from app.theme import apply_theme

    app = QApplication.instance() or QApplication([])
    c = Config()
    check("默认主题浅色", c.theme == "light")
    c.set_theme("dark")
    check("设置深色", c.theme == "dark")
    c.set_theme("invalid")
    check("非法值被拒绝", c.theme == "dark")
    c.set_theme("system")
    check("设置跟随系统", c.theme == "system")

    eff = apply_theme(app, "dark")
    check("深色 QSS 生效", eff == "dark" and "#1e1f24" in app.styleSheet())
    eff = apply_theme(app, "light")
    check("浅色 QSS 生效", eff == "light" and "#f0f2f5" in app.styleSheet())

    from app.main_window import MainWindow
    w = MainWindow()
    checked = [a for a in w.theme_group.actions() if a.isChecked()]
    check("菜单勾选浅色", len(checked) == 1 and checked[0].data() == "light")
    w.close()
    cfg = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
    if os.path.exists(cfg):
        os.remove(cfg)


def test_show_window():
    print("== 展示窗口 ==")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    from app.main_window import MainWindow

    app = QApplication.instance() or QApplication([])
    w = MainWindow()
    w.config.upsert_provider({"uid": "p-a", "provider_id": "deepseek_official",
                              "display_name": "DeepSeek 官方", "enabled": True,
                              "auto_refresh_minutes": 3, "config": {}})
    w._rebuild_cards()
    w.show()
    app.processEvents()
    check("主窗口可见", w.isVisible())
    w._show_site(w.config.providers()[0])
    app.processEvents()
    check("展示窗口已创建", getattr(w, "_show_win", None) is not None)
    check("主窗口已隐藏", not w.isVisible())
    check("展示窗口显示", w._show_win.isVisible())
    # 返回
    w._show_win._back()
    app.processEvents()
    check("返回后主窗口恢复", w.isVisible())
    check("展示窗口已关闭", getattr(w, "_show_win", None) is None)
    w.close()
    cfg = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
    if os.path.exists(cfg):
        os.remove(cfg)


def test_show_window_size():
    print("== 展示窗口大小调整与记忆 ==")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    from app.providers.base import QuotaInfo
    from app.show_window import ShowWindow

    app = QApplication.instance() or QApplication([])
    entry = {"uid": "p-a", "provider_id": "deepseek_official", "display_name": "DeepSeek 官方",
             "enabled": True, "auto_refresh_minutes": 3, "config": {}}
    info = QuotaInfo(ok=True, provider_id="deepseek_official", display_name="DeepSeek 官方",
                     remaining=16.68, total=16.68, currency="CNY", message="ok")

    captured = {}
    # 无 initial_size 时：默认大小 = 背景图（1026x1026）的 30%
    sw0 = ShowWindow(entry, initial_info=info, on_close=lambda s: None)
    check("默认大小为图片 30%", sw0.width() == 307 and sw0.height() == 307,
          f"{sw0.width()}x{sw0.height()}")
    check("背景图已加载", not sw0._bg_pixmap.isNull())
    sw0.close()

    sw = ShowWindow(entry, initial_info=info, on_close=lambda s: captured.update(size=s),
                    initial_size=(350, 420))
    check("固定 1:1 方形", sw.width() == sw.height(), f"{sw.width()}x{sw.height()}")
    # 右下角边缘可触发调整大小模式
    sw.show()
    app.processEvents()
    from PySide6.QtCore import QPoint
    d = sw._hit_test_edge(QPoint(sw.width() - 3, sw.height() // 2))
    check("右下边缘进入调整模式", d & 2 or d & 8, str(d))  # RIGHT=2, BOTTOM=8
    sw.resize(400, 460)
    app.processEvents()
    check("缩放保持 1:1", sw.width() == sw.height(), f"{sw.width()}x{sw.height()}")
    sw.close()
    check("关闭回调带回大小", captured.get("size") == (460, 460), str(captured))

    # 主窗口统一保存与读取
    from app.main_window import MainWindow
    w = MainWindow()
    w.config.upsert_provider(entry)
    w._rebuild_cards()
    w.show()
    app.processEvents()
    w._show_site(w.config.providers()[0])
    app.processEvents()
    w._show_win.resize(390, 450)
    w._show_win._back()
    app.processEvents()
    check("主窗口保存展示窗口大小（方形）",
          w.config.data.get("show_window_size") == {"w": 450, "h": 450},
          str(w.config.data.get("show_window_size")))
    check("返回后主窗口恢复", w.isVisible())
    w.close()
    cfg = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
    if os.path.exists(cfg):
        os.remove(cfg)


if __name__ == "__main__":
    test_config()
    test_config_corrupt()
    test_registry()
    test_provider_parse()
    test_oneapi_parse()
    test_deepseek_parse()
    test_max66_parse()
    test_website_urls()
    test_pin_flag()
    test_dialog_fields_rebuild()
    test_fetch_entry_and_testtask()
    test_retry()
    test_geometry()
    test_http_error_status()
    test_search_and_sort()
    test_fonts()
    test_theme()
    test_show_window()
    test_show_window_size()
    print(f"\n结果：通过 {passed} 项，失败 {failed} 项")
    sys.exit(1 if failed else 0)
