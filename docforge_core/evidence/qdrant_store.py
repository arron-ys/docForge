"""Qdrant Local Persistent storage and filtered evidence retrieval."""

from __future__ import annotations

import json
import logging
import warnings
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from qdrant_client import QdrantClient, models

from docforge_core.domain.enums import AllowedUsage, CorpusType, EvidenceType
from docforge_core.domain.schemas import EvidenceItem
from docforge_core.embedding.base import EmbeddingProvider
from docforge_core.embedding.provider_factory import create_embedding_provider

logger = logging.getLogger(__name__)

PAYLOAD_INDEX_FIELDS = (
    "corpus_type",
    "allowed_usage",
    "source_type",
    "evidence_type",
    "function_name",
    "related_module",
    "tags",
)


class QdrantStore:
    """Persist EvidenceItem vectors in a local Qdrant database."""

    def __init__(
        self,
        data_dir: Path | None = None,
        embedding_provider: EmbeddingProvider | None = None,
    ) -> None:
        if data_dir is None:
            from docforge_core.config.settings import get_settings

            self.qdrant_path = get_settings().docforge_qdrant_path
        else:
            self.qdrant_path = data_dir / "qdrant"
        self.qdrant_path.mkdir(parents=True, exist_ok=True)
        self.embedding_provider = embedding_provider or create_embedding_provider()
        self.client = QdrantClient(path=str(self.qdrant_path))

    def ensure_collection(self, collection_name: str, vector_size: int) -> None:
        if vector_size <= 0:
            raise ValueError("vector_size 必须大于 0")

        if self.client.collection_exists(collection_name):
            info = self.client.get_collection(collection_name)
            vectors = info.config.params.vectors
            existing_size = getattr(vectors, "size", None)
            if existing_size != vector_size:
                raise ValueError(
                    f"collection {collection_name} vector_size={existing_size}，"
                    f"与当前 embedding vector_size={vector_size} 不一致"
                )
            return

        self.client.create_collection(
            collection_name=collection_name,
            vectors_config=models.VectorParams(size=vector_size, distance=models.Distance.COSINE),
        )
        for field_name in PAYLOAD_INDEX_FIELDS:
            try:
                with warnings.catch_warnings(record=True) as caught_warnings:
                    warnings.simplefilter("always")
                    self.client.create_payload_index(
                        collection_name=collection_name,
                        field_name=field_name,
                        field_schema=models.PayloadSchemaType.KEYWORD,
                    )
                for warning in caught_warnings:
                    logger.warning("Qdrant payload index warning for %s: %s", field_name, warning.message)
            except Exception as exc:
                logger.warning("无法为 Qdrant payload 字段 %s 创建索引: %s", field_name, exc)

    def upsert_evidence_items(
        self,
        collection_name: str,
        evidence_items: list[EvidenceItem],
    ) -> int:
        if not evidence_items:
            return 0

        response = self.embedding_provider.embed_texts(
            [self._embedding_text(item) for item in evidence_items]
        )
        if not response.vectors or not response.vectors[0]:
            raise ValueError("embedding provider 返回了空向量")
        vector_size = len(response.vectors[0])
        if any(len(vector) != vector_size for vector in response.vectors):
            raise ValueError("embedding provider 返回的向量维度不一致")

        self.ensure_collection(collection_name, vector_size)
        points = [
            models.PointStruct(
                id=str(uuid5(NAMESPACE_URL, item.evidence_id)),
                vector=vector,
                payload=self._payload(item),
            )
            for item, vector in zip(evidence_items, response.vectors, strict=True)
        ]
        self.client.upsert(collection_name=collection_name, points=points, wait=True)
        return len(points)

    def search(
        self,
        collection_name: str,
        query_text: str,
        top_k: int = 8,
        corpus_type: CorpusType | None = None,
        allowed_usage: AllowedUsage | None = None,
        evidence_type: EvidenceType | None = None,
        tags: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        if not query_text.strip():
            raise ValueError("query_text 不能为空")
        if top_k <= 0:
            raise ValueError("top_k 必须大于 0")
        if not self.client.collection_exists(collection_name):
            return []

        response = self.embedding_provider.embed_texts([query_text])
        vector = response.vectors[0]
        conditions: list[Any] = []
        if corpus_type is not None:
            conditions.append(self._match_value("corpus_type", corpus_type.value))
        if allowed_usage is not None:
            conditions.append(self._match_value("allowed_usage", allowed_usage.value))
        if evidence_type is not None:
            conditions.append(self._match_value("evidence_type", evidence_type.value))
        if tags:
            conditions.append(
                models.FieldCondition(key="tags", match=models.MatchAny(any=tags))
            )

        result = self.client.query_points(
            collection_name=collection_name,
            query=vector,
            query_filter=models.Filter(must=conditions) if conditions else None,
            limit=top_k,
            with_payload=True,
            with_vectors=False,
        )
        return [
            {
                "evidence_id": (point.payload or {}).get("evidence_id"),
                "score": point.score,
                "payload": point.payload or {},
            }
            for point in result.points
        ]

    @staticmethod
    def _match_value(key: str, value: str) -> models.FieldCondition:
        return models.FieldCondition(key=key, match=models.MatchValue(value=value))

    @staticmethod
    def _embedding_text(item: EvidenceItem) -> str:
        facts = json.dumps(item.extracted_facts, ensure_ascii=False)
        return f"{item.summary or ''}\n{facts}\n{' '.join(item.tags)}"

    @staticmethod
    def _payload(item: EvidenceItem) -> dict[str, Any]:
        return {
            "evidence_id": item.evidence_id,
            "source_id": item.source_id,
            "source_type": item.source_type.value,
            "file_type": item.file_type.value,
            "corpus_type": item.corpus_type.value,
            "allowed_usage": item.allowed_usage.value,
            "evidence_type": item.evidence_type.value,
            "evidence_strength": item.evidence_strength.value,
            "function_name": item.function_name,
            "related_module": item.related_module,
            "related_chapter": item.related_chapter,
            "summary": item.summary,
            "tags": item.tags,
            "source_location": item.source_location,
            "confidence": item.confidence,
            "is_confirmed": item.is_confirmed,
            "needs_human_confirmation": item.needs_human_confirmation,
        }
