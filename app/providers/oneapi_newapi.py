"""One-API / New-API / Uni-API 框架 适配器。

国内很多中转站用这套开源框架部署，查余额接口统一为：

    GET {base_url}/api/user/self
    Authorization: Bearer {access_token}

响应示例（new-api 结构）：
    {
      "success": true,
      "message": "",
      "data": {
        "id": 1,
        "username": "user",
        "quota": 4981234,          # 剩余额度（内部单位）
        "used_quota": 18766,       # 已用额度（内部单位）
        "request_count": 123
      }
    }

内部单位换算：框架默认 500000 内部额度 = 1 美元（不同部署可能改比例，
可在站点配置里填「换算比例」字段调整）。

one-api 的响应结构与 new-api 兼容（同样有 quota / used_quota 字段）。
"""

from __future__ import annotations

import requests

from .base import NUMBER, PASSWORD, Provider, ProviderError, QuotaInfo, TEXT


class OneApiProvider(Provider):
    id = "oneapi_newapi"
    name = "One-API / New-API 框架"
    website_url = ""
    description = ("国内主流中转站部署框架（one-api / new-api / uni-api 等）。"
                   "接口：GET /api/user/self，用站点后台生成的 Access Token 鉴权。")

    @classmethod
    def get_website_url(cls, config: dict) -> str:
        return (config or {}).get("base_url", "").rstrip("/") or cls.website_url
    config_schema = [
        {"key": "base_url", "label": "站点地址", "type": TEXT, "required": True,
         "placeholder": "https://chat.example.com", "default": ""},
        {"key": "access_token", "label": "Access Token", "type": PASSWORD, "required": True,
         "placeholder": "站点设置 → 令牌 里生成", "default": ""},
        {"key": "quota_per_dollar", "label": "换算比例（1 美元 = N 额度）", "type": NUMBER,
         "required": False, "default": 500000,
         "placeholder": "框架默认 500000", },
        {"key": "currency", "label": "币种", "type": TEXT, "required": False,
         "placeholder": "USD / CNY，留空默认 CNY", "default": "CNY"},
    ]

    def fetch(self, session: requests.Session) -> QuotaInfo:
        base = (self.cfg("base_url") or "").rstrip("/")
        token = self.cfg("access_token")
        if not base or not token:
            raise ProviderError("缺少站点地址或 Access Token，请先在设置中填写。")

        headers = {"Authorization": f"Bearer {token}"}
        data = self.get_json(session, f"{base}/api/user/self", headers=headers)

        if data.get("success") is False:
            raise ProviderError(str(data.get("message") or "接口返回失败"))
        d = data.get("data") or {}
        if not isinstance(d, dict):
            raise ProviderError(f"响应结构异常：data 不是对象（{type(d).__name__}）")

        quota = self._num(d.get("quota"))          # 剩余（内部单位）
        used = self._num(d.get("used_quota"))      # 已用（内部单位）
        ratio = self._num(self.cfg("quota_per_dollar")) or 500000.0
        if ratio <= 0:
            raise ProviderError("换算比例必须大于 0。")

        remaining_usd = quota / ratio if quota is not None else None
        used_usd = used / ratio if used is not None else None
        total = None
        if remaining_usd is not None and used_usd is not None:
            total = remaining_usd + used_usd

        return QuotaInfo(
            ok=True,
            provider_id=self.id,
            total=total,
            used=used_usd,
            remaining=remaining_usd,
            currency=(self.cfg("currency") or "CNY").strip() or "CNY",
            expires_at="",
            message=f"内部额度剩余 {quota:,.0f}" if quota is not None else "ok",
            raw=data,
        )
