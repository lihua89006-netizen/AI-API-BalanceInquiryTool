"""配置读写：所有数据保存在程序目录下的 config.json。

- 源码运行时：放在项目目录
- 打包成 exe 后：放在 exe 同目录（方便用户直接编辑、备份）
"""

from __future__ import annotations

import json
import logging
import os
import sys
from copy import deepcopy

log = logging.getLogger(__name__)

CONFIG_FILE = "config.json"


def app_dir() -> str:
    """程序所在目录：打包后用 exe 目录，源码运行用项目目录。"""
    if getattr(sys, "frozen", False):  # PyInstaller 打包环境
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def config_path() -> str:
    return os.path.join(app_dir(), CONFIG_FILE)


DEFAULT_CONFIG = {
    "always_on_top": False,     # 窗口置顶
    "auto_refresh_minutes": 0,  # 0 = 不自动刷新
    "theme": "light",           # 主题：light / dark / system（跟随系统）
    "providers": [              # 已配置的站点
        # {"provider_id": "openai_compat", "display_name": "我的中转站",
        #  "enabled": True, "config": {"base_url": "...", "api_key": "..."}}
    ],
}


class Config:
    def __init__(self, data: dict | None = None):
        self.data = data if data is not None else deepcopy(DEFAULT_CONFIG)

    # —— 读取 ——
    @property
    def always_on_top(self) -> bool:
        return bool(self.data.get("always_on_top", False))

    @property
    def theme(self) -> str:
        t = self.data.get("theme", "light")
        return t if t in ("light", "dark", "system") else "light"

    @property
    def auto_refresh_minutes(self) -> int:
        try:
            return max(0, int(self.data.get("auto_refresh_minutes", 0)))
        except (TypeError, ValueError):
            return 0

    def providers(self) -> list[dict]:
        v = self.data.get("providers", [])
        if not isinstance(v, list):
            log.warning("[config] providers 字段类型异常（%s），按空列表处理", type(v).__name__)
            return []
        return v

    def provider_by_uid(self, uid: str) -> dict | None:
        for p in self.providers():
            if p.get("uid") == uid:
                return p
        return None

    # —— 修改 ——
    def set_always_on_top(self, value: bool):
        self.data["always_on_top"] = value

    def set_theme(self, value: str):
        if value in ("light", "dark", "system"):
            self.data["theme"] = value

    def set_auto_refresh_minutes(self, minutes: int):
        self.data["auto_refresh_minutes"] = max(0, int(minutes))

    def upsert_provider(self, entry: dict):
        """新增或按 uid 覆盖一个站点配置。"""
        providers = self.data.setdefault("providers", [])
        uid = entry.get("uid")
        for i, p in enumerate(providers):
            if p.get("uid") == uid:
                providers[i] = entry
                return
        providers.append(entry)

    def remove_provider(self, uid: str):
        self.data["providers"] = [p for p in self.providers() if p.get("uid") != uid]

    # —— 持久化 ——
    def save(self):
        path = config_path()
        tmp = path + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
            os.replace(tmp, path)
        except OSError as e:
            # 目录只读/磁盘满/被杀软锁定时不崩溃，仅记录
            log.warning("[config] 写入 config.json 失败：%s", e)


def load_config() -> Config:
    path = config_path()
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                raise ValueError(f"config.json 顶层不是对象：{type(data).__name__}")
            return Config(data)
        except (json.JSONDecodeError, UnicodeDecodeError, OSError, TypeError, ValueError) as e:
            # 文件损坏/编码错误：先备份再回退默认，避免静默覆盖导致用户数据丢失
            try:
                backup = path + ".bak"
                if os.path.exists(backup):
                    os.remove(backup)
                os.rename(path, backup)
                log.warning("[config] config.json 异常（%s），已备份为 config.json.bak 并重建", e)
            except OSError as e2:
                log.warning("[config] config.json 异常（%s），且备份失败：%s", e, e2)
    cfg = Config()
    cfg.save()  # 首次运行生成默认配置文件，方便用户直接编辑
    return cfg
