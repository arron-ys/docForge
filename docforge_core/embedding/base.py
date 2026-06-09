"""Embedding provider abstractions."""

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field


class EmbeddingResponse(BaseModel):
    vectors: list[list[float]]
    model: str
    provider: str
    raw: dict[str, Any] = Field(default_factory=dict)


class EmbeddingProvider(ABC):
    """Common interface for future vector stores."""

    def embed_texts(self, texts: list[str]) -> EmbeddingResponse:
        if not texts:
            return EmbeddingResponse(vectors=[], model=self.model_name, provider=self.provider_name)
        response = self._embed_texts(texts)
        if len(response.vectors) != len(texts):
            raise ValueError("embedding 返回向量数量与输入文本数量不一致")
        return response

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Provider model name."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Provider name."""

    @abstractmethod
    def _embed_texts(self, texts: list[str]) -> EmbeddingResponse:
        """Embed non-empty texts."""
