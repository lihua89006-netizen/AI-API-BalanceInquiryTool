"""适配器注册表：把所有 Provider 类集中注册，界面和 worker 通过这里查找。

新增一个网站的适配器时：
1. 在 providers/ 下新建一个文件，继承 base.Provider，实现 fetch()；
2. 在 PROVIDERS 列表中注册 [id, 类]。
"""

from .base import Provider, QuotaInfo
from .deepseek import DeepSeekProvider
from .max66 import Max66Provider
from .muteki import Sub2ApiProvider
from .openai_compat import OpenAICompatProvider
from .oneapi_newapi import OneApiProvider
from .tokenrhythm import TokenRhythmProvider

# 注册表：id -> Provider 类。新适配器在这里加一行即可。
PROVIDERS: dict[str, type[Provider]] = {
    OpenAICompatProvider.id: OpenAICompatProvider,
    OneApiProvider.id: OneApiProvider,
    DeepSeekProvider.id: DeepSeekProvider,
    Max66Provider.id: Max66Provider,
    TokenRhythmProvider.id: TokenRhythmProvider,
    Sub2ApiProvider.id: Sub2ApiProvider,
}


def get_provider_class(provider_id: str) -> type[Provider] | None:
    return PROVIDERS.get(provider_id)


def list_provider_classes() -> list[type[Provider]]:
    return list(PROVIDERS.values())
