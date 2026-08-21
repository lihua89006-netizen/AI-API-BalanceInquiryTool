"""Sub2API（api.muteki.site）适配器。

Sub2API - AI API Gateway，实测结构：

1. 登录：
   POST https://api.muteki.site/api/v1/auth/login
   JSON body: {"email": "...", "password": "..."}
   成功响应：{"code": 0, "message": "success",
             "data": {"access_token": "<JWT>", "refresh_token": ..., "expires_in": ..., "user": {...}}}

2. 用户信息 / 余额（核心）：
   GET /api/v1/user/profile  （Authorization: Bearer <access_token>）
   data 字段：
     balance          余额（USD）
     frozen_balance   冻结余额
     total_recharged  累计充值
     username         用户名

3. 用量统计（附加）：
   GET /api/v1/usage/stats
   data: total_tokens / total_cost / total_actual_cost（USD）
"""

from __future__ import annotations

import requests

from .base import PASSWORD, Provider, ProviderError, QuotaInfo, TEXT

API_BASE = "https://api.muteki.site/api/v1"


class Sub2ApiProvider(Provider):
    id = "sub2api"
    name = "Maru Code (Sub2API)"
    website_url = "https://api.muteki.site/login"
    description = "Maru Code / Sub2API AI API Gateway（api.muteki.site）：用邮箱 + 密码登录查询余额（USD，含冻结/累计充值/用量）。"
    config_schema = [
        {"key": "email", "label": "邮箱", "type": TEXT, "required": True,
         "placeholder": "登录邮箱", "default": ""},
        {"key": "password", "label": "密码", "type": PASSWORD, "required": True,
         "placeholder": "登录密码", "default": ""},
    ]

    def fetch(self, session: requests.Session) -> QuotaInfo:
        email = self.cfg("email")
        password = self.cfg("password")
        if not email or not password:
            raise ProviderError("缺少邮箱或密码，请先在设置中填写。")

        # —— 登录拿 token ——
        login = self.post_json(session, f"{API_BASE}/auth/login",
                               {"email": email, "password": password})
        if str(login.get("code")) != "0":
            raise ProviderError(str(login.get("message") or "登录失败"))
        token = (login.get("data") or {}).get("access_token")
        if not token:
            raise ProviderError("登录响应缺少 access_token")

        auth = {"Authorization": f"Bearer {token}"}

        # —— 用户信息 / 余额 ——
        profile = self.get_json(session, f"{API_BASE}/user/profile", headers=auth)
        if str(profile.get("code")) != "0":
            raise ProviderError(str(profile.get("message") or "查询用户信息失败"))
        u = profile.get("data") or {}
        if not isinstance(u, dict):
            raise ProviderError(f"用户信息结构异常：{type(u).__name__}")

        balance = self._num(u.get("balance"))
        frozen = self._num(u.get("frozen_balance"))
        recharged = self._num(u.get("total_recharged"))
        username = str(u.get("username") or "").strip()

        # —— 用量统计（附加，失败不影响主数据） ——
        used_tokens = used_cost = None
        try:
            usage = self.get_json(session, f"{API_BASE}/usage/stats", headers=auth)
            if str(usage.get("code")) == "0":
                sm = usage.get("data") or {}
                used_tokens = self._num(sm.get("total_tokens"))
                used_cost = self._num(sm.get("total_actual_cost") or sm.get("total_cost"))
        except Exception:  # noqa: BLE001 —— 附加信息失败可忽略
            pass

        parts = []
        if username:
            parts.append(f"用户 {username}")
        if frozen:
            parts.append(f"冻结 {frozen:,.4f}")
        if recharged:
            parts.append(f"累计充值 {recharged:,.4f}")
        if used_tokens is not None:
            parts.append(f"Token {used_tokens:,.0f}")
        if used_cost:
            parts.append(f"已消费 ${used_cost:,.4f}")
        extra = "；".join(parts)

        return QuotaInfo(
            ok=True,
            provider_id=self.id,
            total=balance,        # 无“总额”概念，用余额
            used=None,
            remaining=balance,
            currency="USD",
            expires_at="",
            extra=extra,
            message="ok",
            raw=profile,
        )
