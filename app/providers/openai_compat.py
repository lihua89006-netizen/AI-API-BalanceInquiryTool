"""OpenAI 官方 / 兼容中转站 适配器。

覆盖结构（很多中转站沿用 OpenAI 的计费接口）：
    GET {base_url}/v1/dashboard/billing/credit_grants
    Authorization: Bearer {api_key}

响应示例：
    {
      "object": "credit_grants",
      "total_granted": 18.0,
      "total_used": 10.5,
      "total_available": 7.5,
      "grants": {"data": [{"effective_at": ..., "expires_at": ...}]}
    }
"""

from __future__ import annotations

import requests

from .base import NUMBER, PASSWORD, Provider, ProviderError, QuotaInfo, TEXT


class OpenAICompatProvider(Provider):
    id = "openai_compat"
    name = "OpenAI 兼容计费接口"
    website_url = ""
    description = "适用于 OpenAI 官方及沿用 /v1/dashboard/billing/credit_grants 计费结构的中转站。"

    @classmethod
    def get_website_url(cls, config: dict) -> str:
        # 跳转到配置里填的接口地址
        return (config or {}).get("base_url", "").rstrip("/") or cls.website_url
    config_schema = [
        {"key": "base_url", "label": "接口地址", "type": TEXT, "required": True,
         "placeholder": "https://api.openai.com", "default": ""},
        {"key": "api_key", "label": "API Key", "type": PASSWORD, "required": True,
         "placeholder": "sk-...", "default": ""},
        {"key": "currency", "label": "币种", "type": TEXT, "required": False,
         "placeholder": "USD / CNY，留空默认 CNY", "default": "CNY"},
    ]

    def fetch(self, session: requests.Session) -> QuotaInfo:
        base = (self.cfg("base_url") or "").rstrip("/")
        api_key = self.cfg("api_key")
        if not base or not api_key:
            raise ProviderError("缺少接口地址或 API Key，请先在设置中填写。")

        headers = {"Authorization": f"Bearer {api_key}"}
        data = self.get_json(session, f"{base}/v1/dashboard/billing/credit_grants", headers=headers)

        total = self._num(data.get("total_granted"))
        used = self._num(data.get("total_used"))
        remaining = self._num(data.get("total_available"))

        # 过期时间：取 grants.data 里第一个有 expires_at 的
        expires = ""
        try:
            for g in data.get("grants", {}).get("data", []):
                if g.get("expires_at"):
                    expires = str(g["expires_at"])
                    break
        except (AttributeError, TypeError):
            pass

        return QuotaInfo(
            ok=True,
            provider_id=self.id,
            total=total,
            used=used,
            remaining=remaining,
            currency=(self.cfg("currency") or "CNY").strip() or "CNY",
            expires_at=expires,
            message="ok",
            raw=data,
        )
