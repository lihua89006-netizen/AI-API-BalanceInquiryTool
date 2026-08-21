"""后台刷新：网络请求在线程池中执行，通过 Qt 信号回到主线程更新界面。

- fetch_entry(entry): 核心逻辑，单个站点 -> QuotaInfo（线程内调用）
- Refresher.refresh_all(): 为每个启用的站点提交刷新任务
- TestTask: 供「测试连接」使用的单次任务
- 信号 finished(uid, QuotaInfo) 在完成后发出（主线程槽函数接收）
"""

from __future__ import annotations

import logging
import time

import requests
from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

from .providers import get_provider_class
from .providers.base import ProviderError, QuotaInfo

log = logging.getLogger(__name__)

RETRY_DELAY = 0.8  # 网络错误重试前的等待秒数


def fetch_entry(entry: dict, retries: int = 1) -> QuotaInfo:
    """执行一次站点额度查询，返回 QuotaInfo（永不抛异常，错误转成 ok=False）。

    - 业务错误（ProviderError，如登录失败、Key 无效）不重试；
    - 网络/超时类错误自动重试 retries 次。
    """
    info = QuotaInfo(
        provider_id=entry.get("provider_id", ""),
        display_name=entry.get("display_name", ""),
    )
    t0 = time.time()
    for attempt in range(retries + 1):
        try:
            cls = get_provider_class(entry.get("provider_id", ""))
            if cls is None:
                raise ProviderError(f"未知的站点类型：{entry.get('provider_id')}")
            cfg = dict(entry.get("config") or {})
            provider = cls(cfg)
            session = provider._new_session()
            try:
                proxy = cfg.get("proxy") or ""
                if proxy:
                    session.proxies = {"http": proxy, "https": proxy}
                info = provider.fetch(session)
            finally:
                session.close()  # 及时释放连接池/句柄
            info.provider_id = cls.id
            info.display_name = entry.get("display_name") or cls.name
            info.message = info.message or "ok"
            break
        except ProviderError as e:
            info.message = str(e)
            break
        except requests.RequestException as e:
            if attempt < retries:
                log.warning("站点 %s 网络错误（第 %d 次），重试：%s",
                            entry.get("provider_id"), attempt + 1, e)
                time.sleep(RETRY_DELAY)
                continue
            info.message = f"网络错误：{e}"
        except Exception as e:  # noqa: BLE001 —— 兜底，任何异常都变成失败信息
            log.exception("查询站点 %s 失败", entry.get("provider_id"))
            info.message = f"异常：{e}"
            break
    info._elapsed = round(time.time() - t0, 1)
    return info


class _Bridge(QObject):
    """跨线程信号桥。"""
    finished = Signal(str, str, object)  # (batch_id, uid, QuotaInfo)


class _RefreshTask(QRunnable):
    def __init__(self, uid: str, entry: dict, bridge: _Bridge, batch_id: str = ""):
        super().__init__()
        self.uid = uid
        self.entry = entry
        self.bridge = bridge
        self.batch_id = batch_id

    def run(self):
        self.bridge.finished.emit(self.batch_id, self.uid, fetch_entry(self.entry))


class TestBridge(QObject):
    """测试连接任务的信号桥。注意：不要把它挂在对话框父对象下，
    否则对话框提前关闭会导致 worker 线程向已销毁的 C++ 对象 emit。"""

    done = Signal(object)  # (QuotaInfo)


class TestTask(QRunnable):
    def __init__(self, entry: dict, bridge: TestBridge):
        super().__init__()
        self.entry = entry
        self.bridge = bridge

    def run(self):
        info = fetch_entry(self.entry)
        try:
            self.bridge.done.emit(info)
        except RuntimeError:
            # 对话框已销毁（信号桥被回收），静默丢弃结果
            pass


class Refresher(QObject):
    """刷新调度器：持有线程池和信号桥。"""

    finished = Signal(str, str, object)  # 透传桥信号 (batch_id, uid, QuotaInfo)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.bridge = _Bridge()
        self.bridge.finished.connect(self.finished)
        self.pool = QThreadPool.globalInstance()
        self.pool.setMaxThreadCount(4)

    def refresh_all(self, entries: list[dict], batch_id: str = ""):
        """为每个启用的站点提交刷新任务。batch_id 用于区分批次。"""
        for entry in entries:
            uid = entry.get("uid") or entry.get("provider_id", "")
            task = _RefreshTask(uid, entry, self.bridge, batch_id)
            self.pool.start(task)

    def refresh_one(self, entry: dict):
        self.refresh_all([entry])
