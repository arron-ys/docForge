"""Jina embedding provider."""

from typing import Any

import httpx

from docforge_core.config.settings import Settings, get_settings
from docforge_core.llm.base import ProviderError

from .base import EmbeddingProvider, EmbeddingResponse


class JinaEmbeddingProvider(EmbeddingProvider):
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.api_key = self.settings.jina_api_key
        self.model = self.settings.jina_embedding_model or "jina-embeddings-v3"
        if not self.api_key:
            raise ValueError("JINA_API_KEY 未配置")

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
                "https://api.jina.ai/v1/embeddings",
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
