"""Jina embedding provider."""

from typing import Any

import httpx

from docforge_core.config.runtime_model_config import (
    DEFAULT_JINA_BASE_URL,
    RuntimeProviderConfig,
    get_runtime_model_config_service,
)
from docforge_core.config.settings import Settings, get_settings
from docforge_core.llm.base import ProviderError

from .base import EmbeddingProvider, EmbeddingResponse


class JinaEmbeddingProvider(EmbeddingProvider):
    def __init__(
        self,
        settings: Settings | None = None,
        runtime_config: RuntimeProviderConfig | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        if runtime_config is None and settings is None:
            candidate = get_runtime_model_config_service().get_embedding_config()
            if candidate and candidate.provider == "jina":
                runtime_config = candidate

        self.api_key = runtime_config.api_key if runtime_config else self.settings.jina_api_key
        self.model = (
            runtime_config.model
            if runtime_config
            else self.settings.jina_embedding_model or "jina-embeddings-v3"
        )
        self.base_url = (
            runtime_config.base_url
            if runtime_config
            else self.settings.jina_base_url or DEFAULT_JINA_BASE_URL
        )
        if not self.api_key:
            raise ValueError("模型密钥未配置，请在右上角“配置密钥”中填写并测试连接")

    @property
    def model_name(self) -> str:
        return self.model

    @property
    def provider_name(self) -> str:
        return "jina"

    def _embed_texts(self, texts: list[str]) -> EmbeddingResponse:
        payload: dict[str, Any] = {
            "model": self.model,
            "input": texts,
        }
        try:
            response = httpx.post(
                self._embeddings_url(),
                headers={"Authorization": f"Bearer {self.api_key}"},
                json=payload,
                timeout=60,
            )
            response.raise_for_status()
            raw = response.json()
            vectors = [item["embedding"] for item in raw["data"]]
        except Exception as exc:
            raise ProviderError(f"JinaEmbeddingProvider 请求失败: {exc}") from exc

        return EmbeddingResponse(
            vectors=vectors,
            model=self.model,
            provider=self.provider_name,
            raw=raw,
        )

    def _embeddings_url(self) -> str:
        base_url = self.base_url.rstrip("/")
        if base_url.endswith("/embeddings"):
            return base_url
        return f"{base_url}/embeddings"
