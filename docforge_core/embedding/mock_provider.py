"""Mock embedding provider for tests."""

from .base import EmbeddingProvider, EmbeddingResponse


class MockEmbeddingProvider(EmbeddingProvider):
    def __init__(self, vector_size: int = 8) -> None:
        self.vector_size = vector_size

    @property
    def model_name(self) -> str:
        return "mock"

    @property
    def provider_name(self) -> str:
        return "mock"

    def _embed_texts(self, texts: list[str]) -> EmbeddingResponse:
        vectors = [[float(index + 1)] * self.vector_size for index, _ in enumerate(texts)]
        return EmbeddingResponse(
            vectors=vectors,
            model=self.model_name,
            provider=self.provider_name,
            raw={"count": len(texts)},
        )
