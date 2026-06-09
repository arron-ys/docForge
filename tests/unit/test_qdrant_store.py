from pathlib import Path

import pytest

from docforge_core.domain.enums import (
    AllowedUsage,
    CorpusType,
    EvidenceStrength,
    EvidenceType,
    FileType,
    SourceType,
)
from docforge_core.domain.schemas import EvidenceItem
from docforge_core.embedding.mock_provider import MockEmbeddingProvider
from docforge_core.evidence.qdrant_store import QdrantStore


def _product_evidence(evidence_id: str = "ev_product") -> EvidenceItem:
    return EvidenceItem(
        evidence_id=evidence_id,
        source_id="product",
        source_type=SourceType.PRD,
        file_type=FileType.TXT,
        evidence_type=EvidenceType.PRODUCT_DOCUMENT,
        corpus_type=CorpusType.PRODUCT_EVIDENCE,
        allowed_usage=AllowedUsage.FACTUAL_EVIDENCE,
        evidence_strength=EvidenceStrength.MEDIUM,
        summary="产品支持数据集导入",
        tags=["data_platform"],
    )


def _reference_evidence(evidence_id: str = "ev_reference") -> EvidenceItem:
    return EvidenceItem(
        evidence_id=evidence_id,
        source_id="reference",
        source_type=SourceType.REFERENCE_SOFT_COPYRIGHT_DOC,
        file_type=FileType.TXT,
        evidence_type=EvidenceType.REFERENCE_STYLE_ONLY,
        corpus_type=CorpusType.REFERENCE_STYLE,
        allowed_usage=AllowedUsage.STYLE_ONLY,
        evidence_strength=EvidenceStrength.NOT_ALLOWED_AS_FACT,
        summary="参考章节写法",
        tags=["reference_style"],
    )


@pytest.fixture()
def qdrant_store(tmp_path: Path) -> QdrantStore:
    return QdrantStore(data_dir=tmp_path, embedding_provider=MockEmbeddingProvider())


def test_qdrant_store_uses_local_path(tmp_path: Path) -> None:
    store = QdrantStore(data_dir=tmp_path, embedding_provider=MockEmbeddingProvider())

    assert store.qdrant_path == tmp_path / "qdrant"
    assert store.qdrant_path.exists()


def test_upsert_empty_returns_zero(qdrant_store: QdrantStore) -> None:
    assert qdrant_store.upsert_evidence_items("empty", []) == 0


def test_upsert_and_search_respects_isolation_filters(qdrant_store: QdrantStore) -> None:
    items = [_product_evidence(), _reference_evidence()]

    assert qdrant_store.upsert_evidence_items("evidence", items) == 2

    product = qdrant_store.search(
        "evidence",
        "数据集",
        corpus_type=CorpusType.PRODUCT_EVIDENCE,
        allowed_usage=AllowedUsage.FACTUAL_EVIDENCE,
    )
    reference = qdrant_store.search(
        "evidence",
        "章节",
        corpus_type=CorpusType.REFERENCE_STYLE,
        allowed_usage=AllowedUsage.STYLE_ONLY,
    )

    assert [item["evidence_id"] for item in product] == ["ev_product"]
    assert [item["evidence_id"] for item in reference] == ["ev_reference"]
    assert product[0]["payload"]["corpus_type"] == CorpusType.PRODUCT_EVIDENCE.value
    assert product[0]["payload"]["allowed_usage"] == AllowedUsage.FACTUAL_EVIDENCE.value
    assert product[0]["payload"]["evidence_type"] == EvidenceType.PRODUCT_DOCUMENT.value
    assert product[0]["payload"]["tags"] == ["data_platform"]


def test_search_supports_evidence_type_and_tags(qdrant_store: QdrantStore) -> None:
    qdrant_store.upsert_evidence_items("evidence", [_product_evidence(), _reference_evidence()])

    result = qdrant_store.search(
        "evidence",
        "数据",
        evidence_type=EvidenceType.PRODUCT_DOCUMENT,
        tags=["data_platform"],
    )

    assert [item["evidence_id"] for item in result] == ["ev_product"]


def test_search_validates_query_and_top_k(qdrant_store: QdrantStore) -> None:
    with pytest.raises(ValueError, match="query_text"):
        qdrant_store.search("missing", " ")
    with pytest.raises(ValueError, match="top_k"):
        qdrant_store.search("missing", "query", top_k=0)


def test_missing_collection_returns_empty(qdrant_store: QdrantStore) -> None:
    assert qdrant_store.search("missing", "query") == []


def test_existing_collection_vector_size_mismatch_raises(qdrant_store: QdrantStore) -> None:
    qdrant_store.ensure_collection("evidence", vector_size=8)

    with pytest.raises(ValueError, match="vector_size"):
        qdrant_store.ensure_collection("evidence", vector_size=4)
