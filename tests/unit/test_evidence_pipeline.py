from pathlib import Path

from docforge_core.domain.enums import CorpusType, SourceType
from docforge_core.embedding.mock_provider import MockEmbeddingProvider
from docforge_core.evidence.evidence_pipeline_service import EvidencePipelineService
from docforge_core.io.file_registry import SourceFileRegistry
from docforge_core.io.state_store import StateStore
from docforge_core.parsers.source_parsing_service import SourceParsingService


def test_pipeline_builds_indexes_and_retrieves_isolated_evidence(tmp_path: Path) -> None:
    store = StateStore(data_dir=tmp_path)
    state = store.create_initial_state()
    registry = SourceFileRegistry(state.run_id, data_dir=tmp_path)
    product = registry.register_product_file("prd.txt", "数据集导入".encode(), SourceType.PRD)
    reference = registry.register_reference_file("reference.txt", "章节写法".encode())
    store.add_source_item(state.run_id, product)
    store.add_source_item(state.run_id, reference)
    SourceParsingService(data_dir=tmp_path).parse_run(state.run_id)
    pipeline = EvidencePipelineService(
        data_dir=tmp_path,
        embedding_provider=MockEmbeddingProvider(),
    )

    indexed_state = pipeline.build_and_index_run(state.run_id)
    product_results = pipeline.qdrant_store.search(
        indexed_state.qdrant_collection,
        "数据集",
        corpus_type=CorpusType.PRODUCT_EVIDENCE,
    )
    reference_results = pipeline.qdrant_store.search(
        indexed_state.qdrant_collection,
        "章节",
        corpus_type=CorpusType.REFERENCE_STYLE,
    )

    assert len(indexed_state.evidence_map) == 2
    assert {item["payload"]["corpus_type"] for item in product_results} == {
        CorpusType.PRODUCT_EVIDENCE.value
    }
    assert {item["payload"]["corpus_type"] for item in reference_results} == {
        CorpusType.REFERENCE_STYLE.value
    }
