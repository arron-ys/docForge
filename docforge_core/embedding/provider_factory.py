"""Embedding provider factory."""

from docforge_core.config.runtime_model_config import get_runtime_model_config_service
from docforge_core.config.settings import Settings, get_settings

from .base import EmbeddingProvider
from .jina_embedding_provider import JinaEmbeddingProvider
from .mock_provider import MockEmbeddingProvider


def create_embedding_provider(settings: Settings | None = None) -> EmbeddingProvider:
    resolved_settings = settings or get_settings()
    if settings is None:
        runtime_config = get_runtime_model_config_service().get_embedding_config()
        if runtime_config and runtime_config.provider == "jina":
            return JinaEmbeddingProvider(settings=resolved_settings, runtime_config=runtime_config)

    provider = resolved_settings.default_embedding_provider.lower()
    if provider == "jina":
        return JinaEmbeddingProvider(settings=resolved_settings)
    if provider == "mock":
        return MockEmbeddingProvider()
    raise ValueError(f"不支持的 Embedding provider: {resolved_settings.default_embedding_provider}")
