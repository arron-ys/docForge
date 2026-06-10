from __future__ import annotations

from pathlib import Path

from docforge_core.config.runtime_model_config import (
    DEFAULT_JINA_BASE_URL,
    RuntimeModelConfigService,
    RuntimeProviderConfigUpdate,
)


def test_runtime_model_config_saves_loads_and_masks_without_full_key(
    tmp_path: Path,
) -> None:
    service = RuntimeModelConfigService(tmp_path / "model_config.json")

    saved = service.update_config(
        llm=RuntimeProviderConfigUpdate(
            provider="qwen",
            model="qwen-plus",
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            api_key="unit-llm-secret-12345678",
        ),
        embedding=RuntimeProviderConfigUpdate(
            provider="jina",
            model="jina-embeddings-v3",
            base_url=DEFAULT_JINA_BASE_URL,
            api_key="unit-embedding-secret-87654321",
        ),
    )

    loaded = service.load_config()

    assert saved.llm is not None
    assert loaded.llm is not None
    assert loaded.llm.provider == "qwen"
    assert loaded.llm.api_key == "unit-llm-secret-12345678"
    assert loaded.embedding is not None
    assert loaded.embedding.base_url == DEFAULT_JINA_BASE_URL
    assert service.mask_api_key(loaded.llm.api_key) == "unit****5678"


def test_runtime_model_config_empty_api_key_preserves_saved_key(tmp_path: Path) -> None:
    service = RuntimeModelConfigService(tmp_path / "model_config.json")
    service.update_config(
        llm=RuntimeProviderConfigUpdate(
            provider="qwen",
            model="qwen-plus",
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            api_key="unit-existing-llm-secret",
        )
    )

    service.update_config(
        llm=RuntimeProviderConfigUpdate(
            provider="qwen",
            model="qwen-max",
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            api_key="",
        )
    )

    loaded = service.load_config()

    assert loaded.llm is not None
    assert loaded.llm.model == "qwen-max"
    assert loaded.llm.api_key == "unit-existing-llm-secret"


def test_runtime_model_config_can_clear_api_key(tmp_path: Path) -> None:
    service = RuntimeModelConfigService(tmp_path / "model_config.json")
    service.update_config(
        embedding=RuntimeProviderConfigUpdate(
            provider="jina",
            model="jina-embeddings-v3",
            base_url=DEFAULT_JINA_BASE_URL,
            api_key="unit-existing-embedding-secret",
        )
    )

    service.update_config(
        embedding=RuntimeProviderConfigUpdate(
            provider="jina",
            model="jina-embeddings-v3",
            base_url=DEFAULT_JINA_BASE_URL,
            clear_api_key=True,
        )
    )

    loaded = service.load_config()

    assert loaded.embedding is not None
    assert loaded.embedding.api_key == ""
    assert service.get_embedding_config() is None
