"""适配器注册表：把所有 Provider 类集中注册，界面和 worker 通过这里查找。

新增一个网站的适配器时：
1. 在 providers/ 下新建一个文件，继承 base.Provider，实现 fetch()；
2. 在 PROVIDERS 列表中注册 [id, 类]。
"""

from .base import Provider, QuotaInfo
from .deepseek import DeepSeekProvider
from .max66 import Max66Provider
from .openai_compat import OpenAICompatProvider
from .oneapi_newapi import OneApiProvider

# 注册表：id -> Provider 类。新适配器在这里加一行即可。
PROVIDERS: dict[str, type[Provider]] = {
    OpenAICompatProvider.id: OpenAICompatProvider,
    OneApiProvider.id: OneApiProvider,
    DeepSeekProvider.id: DeepSeekProvider,
    Max66Provider.id: Max66Provider,
}

# 扩展适配器（不随 GitHub 发布：tokenrhythm.py / muteki.py 被 .gitignore 排除，
# 只存在于本地；发布版构建时文件缺失 → 自动跳过，不影响其余适配器）
try:
    from .muteki import Sub2ApiProvider
    from .tokenrhythm import TokenRhythmProvider

    PROVIDERS[TokenRhythmProvider.id] = TokenRhythmProvider
    PROVIDERS[Sub2ApiProvider.id] = Sub2ApiProvider
except ImportError:
    pass  # 发布版（无这两个文件）时跳过


def get_provider_class(provider_id: str) -> type[Provider] | None:
    return PROVIDERS.get(provider_id)


def list_provider_classes() -> list[type[Provider]]:
    return list(PROVIDERS.values())
