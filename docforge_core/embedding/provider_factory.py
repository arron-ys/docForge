"""Embedding provider factory."""

from docforge_core.config.settings import Settings, get_settings

from .base import EmbeddingProvider
from .jina_embedding_provider import JinaEmbeddingProvider
from .mock_provider import MockEmbeddingProvider


def create_embedding_provider(settings: Settings | None = None) -> EmbeddingProvider:
    resolved_settings = settings or get_settings()
    provider = resolved_settings.default_embedding_provider.lower()
    if provider == "jina":
        return JinaEmbeddingProvider(settings=resolved_settings)
    if provider == "mock":
        return MockEmbeddingProvider()
    raise ValueError(f"不支持的 Embedding provider: {resolved_settings.default_embedding_provider}")
