"""Provider 抽象基类 —— 所有网站适配器统一实现这个接口。

新增一个网站的适配器步骤：
1. 继承 Provider；
2. 设置 id / name / description / config_schema（UI 会根据 schema 自动生成配置表单）；
3. 实现 fetch(session) -> QuotaInfo；
4. 在 providers/__init__.py 的 PROVIDERS 注册表里注册。
"""

from __future__ import annotations

from dataclasses import dataclass, field

import requests

# 可选字段枚举（UI 表单类型）
TEXT = "text"        # 单行文本
PASSWORD = "password"  # 密码（API key 等，隐藏显示）
NUMBER = "number"    # 数字


@dataclass
class QuotaInfo:
    """一次额度查询的结果。"""

    ok: bool = False                      # 是否成功
    provider_id: str = ""
    display_name: str = ""                # 站点在界面上的显示名
    message: str = ""                     # 错误信息或状态说明
    # —— 额度字段，成功时填充 ——
    total: float | None = None            # 总额度
    used: float | None = None             # 已用
    remaining: float | None = None        # 剩余
    currency: str = "USD"                 # 币种
    expires_at: str = ""                  # 过期时间（原样文本）
    extra: str = ""                       # 附加信息（如剩余次数、赠送余额等），显示在卡片“其他”行
    raw: dict = field(default_factory=dict)  # 原始响应，便于排查


class ProviderError(Exception):
    """适配器内部可抛出此异常，worker 会转成 QuotaInfo(ok=False)。"""


class Provider:
    """所有网站适配器的基类。"""

    id: str = "base"
    name: str = "未命名站点"
    description: str = ""
    # 网站主页（点击卡片上的类型名会跳转到这里）；可在子类覆盖
    website_url: str = ""
    # 配置字段定义，UI 根据它动态生成表单：
    #   {"key": "base_url", "label": "接口地址", "type": TEXT, "required": True,
    #    "placeholder": "https://api.example.com", "default": ""}
    config_schema: list[dict] = []

    def __init__(self, config: dict):
        # config 是用户填写的该站点配置（如 api_key、base_url）
        self.config = config or {}

    @classmethod
    def get_website_url(cls, config: dict) -> str:
        """点击类型名时跳转的网站地址；子类可按配置动态生成（如 base_url）。"""
        return cls.website_url

    def cfg(self, key: str, default=""):
        return (self.config or {}).get(key, default)

    # —— 子类必须实现 ——
    def fetch(self, session: requests.Session) -> QuotaInfo:
        raise NotImplementedError

    # —— 工具方法 ——
    @staticmethod
    def _new_session(timeout: int = 30) -> requests.Session:
        s = requests.Session()
        s.headers.update({"User-Agent": "ApiQuotaMonitor/1.0"})
        s.timeout = timeout
        return s

    def get_json(self, session: requests.Session, url: str, headers: dict | None = None) -> dict:
        """GET 并解析 JSON，统一处理错误。"""
        resp = session.get(url, headers=headers)
        return self._parse_json_response(resp, url)

    def post_json(self, session: requests.Session, url: str, json_body: dict, headers: dict | None = None) -> dict:
        resp = session.post(url, json=json_body, headers=headers)
        return self._parse_json_response(resp, url)

    def _parse_json_response(self, resp, url: str) -> dict:
        """校验 HTTP 状态码并解析 JSON；错误响应抛出 ProviderError。"""
        try:
            data = resp.json()
        except ValueError:
            raise ProviderError(
                f"响应不是 JSON（HTTP {resp.status_code}）：{resp.text[:200]}"
            )
        if resp.status_code >= 400:
            detail = data.get("message") or data.get("detail") or data.get("error") or resp.text[:200]
            if isinstance(detail, dict):
                detail = str(detail.get("message", detail))[:200]
            raise ProviderError(f"HTTP {resp.status_code}：{detail}")
        if not isinstance(data, dict):
            raise ProviderError(f"响应结构异常：{type(data).__name__}")
        return data

    def _num(self, v) -> float | None:
        """宽松地把任意值转成 float，转不了返回 None。"""
        if v is None or v == "":
            return None
        try:
            return float(v)
        except (TypeError, ValueError):
            return None
