"""基元律动（tokenrhythm.studio）适配器。

OpenSquilla / 基元律动 AI API 平台，实测结构：

1. 登录（会话 cookie）：
   POST https://tokenrhythm.studio/api/auth/login
   JSON body: {"account": "<用户名>", "password": "<密码>"}
   成功响应：{"code": 0, "message": "ok", "data": {"user": {...}}}
   并下发 tr_session / tr_csrf cookie（HttpOnly，requests.Session 自动保持）

2. 钱包余额（核心）：
   GET https://tokenrhythm.studio/api/wallet/summary
   成功响应 data 字段：
     availableBalanceCny  实际可用总额（CNY，字符串）
     giftAvailableCny     已到账赠送额度
     rechargeBalanceCny   充值余额
     debtBalanceCny       欠费余额
     frozenBalanceCny     冻结余额
     currency             "CNY"

3. 用量统计（附加信息）：
   GET https://tokenrhythm.studio/api/usage/panel
   data.summary: calls（调用次数）、totalTokens、costCny（累计花费，元）
"""

from __future__ import annotations

import requests

from .base import PASSWORD, Provider, ProviderError, QuotaInfo, TEXT

API_BASE = "https://tokenrhythm.studio"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) ApiQuotaMonitor/1.0"


class TokenRhythmProvider(Provider):
    id = "tokenrhythm"
    name = "基元律动 (tokenrhythm.studio)"
    website_url = "https://tokenrhythm.studio/account/profile"
    description = ("OpenSquilla / 基元律动 AI API 平台。"
                   "用「用户名 + 密码」登录查询钱包余额（赠送/充值/欠费/冻结）与用量。"
                   "注意登录用的是用户名，不是手机号。")
    config_schema = [
        {"key": "account", "label": "登录用户名", "type": TEXT, "required": True,
         "placeholder": "登录用户名", "default": ""},
        {"key": "password", "label": "密码", "type": PASSWORD, "required": True,
         "placeholder": "登录密码", "default": ""},
    ]

    def _login(self, session: requests.Session):
        account = self.cfg("account")
        password = self.cfg("password")
        if not account or not password:
            raise ProviderError("缺少用户名或密码，请先在设置中填写。")
        session.headers.update({"User-Agent": UA})
        resp = session.post(f"{API_BASE}/api/auth/login",
                            json={"account": account, "password": password})
        try:
            data = resp.json()
        except ValueError:
            raise ProviderError(f"登录响应不是 JSON（HTTP {resp.status_code}）：{resp.text[:200]}")
        if resp.status_code >= 400 or str(data.get("code")) not in ("0",):
            raise ProviderError(f"登录失败：{data.get('message') or data.get('detail') or f'HTTP {resp.status_code}'}")

    def fetch(self, session: requests.Session) -> QuotaInfo:
        self._login(session)

        # —— 钱包余额 ——
        wallet = self.get_json(session, f"{API_BASE}/api/wallet/summary")
        if str(wallet.get("code")) != "0":
            raise ProviderError(str(wallet.get("message") or "查询钱包余额失败"))
        d = wallet.get("data") or {}
        if not isinstance(d, dict):
            raise ProviderError(f"钱包数据结构异常：{type(d).__name__}")

        available = self._num(d.get("availableBalanceCny"))
        currency = str(d.get("currency") or "CNY")

        # —— 用量统计（附加，失败不影响主数据） ——
        calls = tokens = cost_cny = None
        try:
            usage = self.get_json(session, f"{API_BASE}/api/usage/panel")
            if str(usage.get("code")) == "0":
                sm = (usage.get("data") or {}).get("summary") or {}
                calls = self._num(sm.get("calls"))
                tokens = self._num(sm.get("totalTokens"))
                cost_cny = self._num(sm.get("costCny"))
        except Exception:  # noqa: BLE001 —— 附加信息失败可忽略
            pass

        parts = []
        gift = self._num(d.get("giftAvailableCny"))
        if gift is not None:
            parts.append(f"赠送 {gift:,.2f}")
        recharge = self._num(d.get("rechargeBalanceCny"))
        if recharge is not None:
            parts.append(f"充值 {recharge:,.2f}")
        debt = self._num(d.get("debtBalanceCny"))
        if debt:
            parts.append(f"欠费 {debt:,.2f}")
        frozen = self._num(d.get("frozenBalanceCny"))
        if frozen:
            parts.append(f"冻结 {frozen:,.2f}")
        if calls is not None:
            parts.append(f"调用 {calls:.0f} 次")
        if tokens is not None:
            parts.append(f"Token {tokens:,.0f}")
        if cost_cny is not None:
            parts.append(f"累计花费 ¥{cost_cny:,.2f}")
        extra = "；".join(parts)

        return QuotaInfo(
            ok=True,
            provider_id=self.id,
            total=available,      # 无“总额”概念，用可用余额
            used=None,
            remaining=available,
            currency=currency,
            expires_at="",
            extra=extra,
            message="ok",
            raw=wallet,
        )
