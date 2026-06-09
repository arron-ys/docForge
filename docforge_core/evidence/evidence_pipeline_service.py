"""Evidence extraction and indexing orchestration for Sprint 5."""

from pathlib import Path

from docforge_core.domain.schemas import DocForgeState
from docforge_core.embedding.base import EmbeddingProvider
from docforge_core.io.state_store import StateStore

from .extractor import EvidenceExtractorService
from .qdrant_store import QdrantStore


class EvidencePipelineService:
    """Build a run evidence map and index it into local Qdrant."""

    def __init__(
        self,
        data_dir: Path | None = None,
        embedding_provider: EmbeddingProvider | None = None,
    ) -> None:
        self.extractor = EvidenceExtractorService(data_dir=data_dir)
        self.qdrant_store = QdrantStore(
            data_dir=data_dir,
            embedding_provider=embedding_provider,
        )
        self.state_store = StateStore(data_dir=data_dir)

    def build_and_index_run(self, run_id: str) -> DocForgeState:
        state = self.extractor.extract_run(run_id)
        self.qdrant_store.upsert_evidence_items(state.qdrant_collection, state.evidence_map)
        self.state_store.save_state(state)
        return state
