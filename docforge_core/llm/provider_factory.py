"""LLM provider factory."""

from docforge_core.config.settings import Settings, get_settings

from .base import LLMProvider
from .deepseek_provider import DeepSeekProvider
from .mock_provider import MockLLMProvider
from .qwen_provider import QwenProvider


def create_llm_provider(settings: Settings | None = None) -> LLMProvider:
    resolved_settings = settings or get_settings()
    provider = resolved_settings.default_llm_provider.lower()
    if provider == "qwen":
        return QwenProvider(settings=resolved_settings)
    if provider == "deepseek":
        return DeepSeekProvider(settings=resolved_settings)
    if provider == "mock":
        return MockLLMProvider()
    raise ValueError(f"不支持的 LLM provider: {resolved_settings.default_llm_provider}")
