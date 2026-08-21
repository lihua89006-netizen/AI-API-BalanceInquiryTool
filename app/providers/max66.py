"""MaxAI 中转站（max66.xyz）适配器。

结构（已实测确认）：
1. 登录：POST https://max66.xyz/user/login
   form-data: email, password
   成功响应（JSON，并下发 cookie token）：
     {"ok": true, "api_key": "sk-...", "email_verified": true,
      "remaining_calls": 0,           # 剩余次数（次数资源包）
      "paygo_balance": 4.105,         # 按量余额（人民币元）
      "verify_hint": ""}

2. 控制台页：GET /user/dashboard（SSR HTML），可解析“今日已用”：
     <div class="stat"><div class="v">0</div><div class="l">今日已用</div></div>

计费方式：不限量套餐（包时）/ 次数资源包（按次）/ 按量余额（按 token 扣费）。
本适配器展示：剩余=按量余额（CNY），附加信息=剩余次数、今日已用。
"""

from __future__ import annotations

import re

import requests

from .base import PASSWORD, Provider, ProviderError, QuotaInfo, TEXT

LOGIN_URL = "https://max66.xyz/user/login"
DASH_URL = "https://max66.xyz/user/dashboard"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) ApiQuotaMonitor/1.0"


class Max66Provider(Provider):
    id = "max66_zhongzhuan"
    name = "MaxAI 中转站 (max66.xyz)"
    website_url = "https://max66.xyz/user/dashboard"
    description = "MaxAI 大模型 API 中转站：用账号密码登录查询余额（剩余次数 + 按量余额 + 今日已用）。"
    config_schema = [
        {"key": "email", "label": "账号邮箱", "type": TEXT, "required": True,
         "placeholder": "登录邮箱", "default": ""},
        {"key": "password", "label": "密码", "type": PASSWORD, "required": True,
         "placeholder": "登录密码", "default": ""},
    ]

    def fetch(self, session: requests.Session) -> QuotaInfo:
        email = self.cfg("email")
        password = self.cfg("password")
        if not email or not password:
            raise ProviderError("缺少邮箱或密码，请先在设置中填写。")

        session.headers.update({"User-Agent": UA})
        resp = session.post(LOGIN_URL, data={"email": email, "password": password})
        try:
            data = resp.json()
        except ValueError:
            raise ProviderError(f"登录响应不是 JSON（HTTP {resp.status_code}）：{resp.text[:200]}")

        if not data.get("ok"):
            raise ProviderError(str(data.get("message") or data.get("detail") or "登录失败，请检查邮箱和密码"))

        remaining_calls = self._num(data.get("remaining_calls"))
        paygo = self._num(data.get("paygo_balance"))

        # 今日已用：解析控制台页（失败不影响主数据）
        today_used = None
        try:
            d = session.get(DASH_URL)
            m = re.search(r'<div class="v">([^<]*)</div>\s*<div class="l">今日已用</div>', d.text)
            if m:
                today_used = self._num(m.group(1).replace("¥", "").replace(",", "").strip())
        except Exception:  # noqa: BLE001 —— 附加信息失败可忽略
            pass

        parts = []
        parts.append(f"剩余次数 {remaining_calls:.0f}" if remaining_calls is not None else "剩余次数 -")
        if today_used is not None:
            parts.append(f"今日已用 {today_used:g}")
        extra = "；".join(parts)

        return QuotaInfo(
            ok=True,
            provider_id=self.id,
            total=paygo,          # 按量余额即当前可用资金
            used=None,            # 无累计已用概念
            remaining=paygo,
            currency="CNY",
            expires_at="",
            extra=extra,
            message="ok",
            raw=data,
        )
