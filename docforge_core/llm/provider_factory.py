"""LLM provider factory."""

from docforge_core.config.runtime_model_config import get_runtime_model_config_service
from docforge_core.config.settings import Settings, get_settings

from .base import LLMProvider
from .deepseek_provider import DeepSeekProvider
from .mock_provider import MockLLMProvider
from .qwen_provider import QwenProvider


def create_llm_provider(settings: Settings | None = None) -> LLMProvider:
    resolved_settings = settings or get_settings()
    if settings is None:
        runtime_config = get_runtime_model_config_service().get_llm_config()
        if runtime_config and runtime_config.provider == "qwen":
            return QwenProvider(settings=resolved_settings, runtime_config=runtime_config)

    provider = resolved_settings.default_llm_provider.lower()
    if provider == "qwen":
        return QwenProvider(settings=resolved_settings)
    if provider == "deepseek":
        return DeepSeekProvider(settings=resolved_settings)
    if provider == "mock":
        return MockLLMProvider()
    raise ValueError(f"不支持的 LLM provider: {resolved_settings.default_llm_provider}")
