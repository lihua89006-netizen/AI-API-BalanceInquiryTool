"""DeepSeek 官方 API 适配器。

接口（官方文档：Get User Balance）：
    GET https://api.deepseek.com/user/balance
    Authorization: Bearer {api_key}

响应示例（真实返回）：
    {
      "is_available": true,
      "balance_infos": [
        {
          "currency": "CNY",
          "total_balance": "16.71",
          "granted_balance": "0.00",
          "topped_up_balance": "16.71"
        }
      ]
    }

字段说明：
- total_balance   总余额（剩余可用）
- granted_balance 赠送余额
- topped_up_balance 充值余额
- 金额为字符串，本适配器统一转成 float
- DeepSeek 不提供「已用」概念，used 置空显示 "-"
"""

from __future__ import annotations

import requests

from .base import PASSWORD, Provider, ProviderError, QuotaInfo

API_BASE = "https://api.deepseek.com"


class DeepSeekProvider(Provider):
    id = "deepseek_official"
    name = "DeepSeek 官方"
    website_url = "https://platform.deepseek.com/usage"
    description = "DeepSeek 官方 API 余额。接口固定为 https://api.deepseek.com/user/balance，只需填 API Key。"
    config_schema = [
        {"key": "api_key", "label": "API Key", "type": PASSWORD, "required": True,
         "placeholder": "sk-...（platform.deepseek.com 后台获取）", "default": ""},
    ]

    def fetch(self, session: requests.Session) -> QuotaInfo:
        api_key = self.cfg("api_key")
        if not api_key:
            raise ProviderError("缺少 API Key，请先在设置中填写。")

        headers = {"Authorization": f"Bearer {api_key}"}
        data = self.get_json(session, f"{API_BASE}/user/balance", headers=headers)

        if data.get("is_available") is False:
            raise ProviderError("账户当前不可用（is_available=false），请到 DeepSeek 平台确认状态。")

        infos = data.get("balance_infos") or []
        if not isinstance(infos, list) or not infos:
            raise ProviderError("响应中没有 balance_infos 数据。")
        first = infos[0]
        if not isinstance(first, dict):
            raise ProviderError(f"balance_infos 条目结构异常：{type(first).__name__}")

        currency = str(first.get("currency") or "CNY")
        total = self._num(first.get("total_balance"))
        granted = self._num(first.get("granted_balance"))
        topped = self._num(first.get("topped_up_balance"))

        # 多个币种时拼接信息（目前官方只返回 CNY）
        if len(infos) > 1:
            parts = []
            for it in infos:
                if isinstance(it, dict):
                    parts.append(f"{it.get('currency')}:{it.get('total_balance')}")
            extra = "；".join(parts)
        else:
            extra = ""

        msg = f"充值 {fmt_amt(topped)} + 赠送 {fmt_amt(granted)}"
        if extra:
            msg += f"（{extra}）"

        return QuotaInfo(
            ok=True,
            provider_id=self.id,
            total=total,
            used=None,          # DeepSeek 无「已用」概念
            remaining=total,    # 剩余 = 总余额
            currency=currency,
            expires_at="",      # DeepSeek 余额无过期时间
            message=msg,
            raw=data,
        )


def fmt_amt(v) -> str:
    if v is None:
        return "-"
    return f"{v:,.2f}"
