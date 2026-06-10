import pytest

import docforge_core.embedding.jina_embedding_provider as jina_provider_module
import docforge_core.embedding.provider_factory as embedding_provider_factory
from docforge_core.config.runtime_model_config import RuntimeProviderConfig
from docforge_core.config.settings import Settings
from docforge_core.embedding.base import EmbeddingProvider, EmbeddingResponse
from docforge_core.embedding.jina_embedding_provider import JinaEmbeddingProvider
from docforge_core.embedding.mock_provider import MockEmbeddingProvider
from docforge_core.embedding.provider_factory import create_embedding_provider


def test_mock_embedding_provider_returns_matching_vector_count() -> None:
    response = MockEmbeddingProvider().embed_texts(["a", "b"])

    assert len(response.vectors) == 2


def test_mock_embedding_provider_empty_input_returns_empty_vectors() -> None:
    response = MockEmbeddingProvider().embed_texts([])

    assert response.vectors == []


def test_mock_embedding_provider_vector_size_takes_effect() -> None:
    response = MockEmbeddingProvider(vector_size=3).embed_texts(["a"])

    assert len(response.vectors[0]) == 3


def test_embedding_provider_mismatched_vector_count_raises_value_error() -> None:
    class BadEmbeddingProvider(EmbeddingProvider):
        @property
        def model_name(self) -> str:
            return "bad"

        @property
        def provider_name(self) -> str:
            return "bad"

        def _embed_texts(self, texts: list[str]) -> EmbeddingResponse:
            return EmbeddingResponse(vectors=[], model="bad", provider="bad")

    with pytest.raises(ValueError, match="数量"):
        BadEmbeddingProvider().embed_texts(["a"])


def test_embedding_provider_factory_can_create_mock_provider() -> None:
    provider = create_embedding_provider(Settings(default_embedding_provider="mock"))

    assert isinstance(provider, MockEmbeddingProvider)


def test_embedding_provider_factory_unknown_provider_raises_value_error() -> None:
    with pytest.raises(ValueError):
        create_embedding_provider(Settings(default_embedding_provider="unknown"))


def test_jina_embedding_provider_missing_api_key_raises_clear_error() -> None:
    with pytest.raises(ValueError, match="模型密钥未配置"):
        JinaEmbeddingProvider(Settings(jina_api_key=""))


def test_embedding_provider_tests_do_not_require_network() -> None:
    response = MockEmbeddingProvider().embed_texts(["offline"])

    assert response.provider == "mock"


def test_embedding_provider_factory_prefers_runtime_jina_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime_config = RuntimeProviderConfig(
        provider="jina",
        model="jina-embeddings-v3",
        base_url="https://runtime.example/v1",
        api_key="runtime-key",
    )

    class RuntimeService:
        def get_embedding_config(self) -> RuntimeProviderConfig:
            return runtime_config

    monkeypatch.setattr(
        embedding_provider_factory,
        "get_runtime_model_config_service",
        lambda: RuntimeService(),
    )
    monkeypatch.setattr(
        embedding_provider_factory,
        "get_settings",
        lambda: Settings(
            default_embedding_provider="jina",
            jina_api_key="env-key",
            jina_embedding_model="env-model",
        ),
    )

    provider = create_embedding_provider()
    explicit_settings_provider = create_embedding_provider(
        Settings(
            default_embedding_provider="jina",
            jina_api_key="env-key",
            jina_embedding_model="env-model",
        )
    )

    assert isinstance(provider, JinaEmbeddingProvider)
    assert provider.api_key == "runtime-key"
    assert provider.model_name == "jina-embeddings-v3"
    assert provider._embeddings_url() == "https://runtime.example/v1/embeddings"
    assert explicit_settings_provider.provider_name == "jina"
    assert isinstance(explicit_settings_provider, JinaEmbeddingProvider)
    assert explicit_settings_provider.api_key == "env-key"


def test_jina_provider_default_constructor_prefers_runtime_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime_config = RuntimeProviderConfig(
        provider="jina",
        model="jina-embeddings-v3",
        base_url="https://runtime.example/v1",
        api_key="runtime-key",
    )

    class RuntimeService:
        def get_embedding_config(self) -> RuntimeProviderConfig:
            return runtime_config

    monkeypatch.setattr(
        jina_provider_module,
        "get_runtime_model_config_service",
        lambda: RuntimeService(),
    )
    monkeypatch.setattr(
        jina_provider_module,
        "get_settings",
        lambda: Settings(
            default_embedding_provider="jina",
            jina_api_key="env-key",
            jina_embedding_model="env-model",
            jina_base_url="https://env.example/v1",
        ),
    )

    provider = JinaEmbeddingProvider()
    explicit_settings_provider = JinaEmbeddingProvider(
        Settings(
            jina_api_key="env-key",
            jina_embedding_model="env-model",
            jina_base_url="https://env.example/v1",
        )
    )

    assert provider.api_key == "runtime-key"
    assert provider._embeddings_url() == "https://runtime.example/v1/embeddings"
    assert explicit_settings_provider.api_key == "env-key"
    assert explicit_settings_provider._embeddings_url() == "https://env.example/v1/embeddings"
