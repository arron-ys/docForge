from __future__ import annotations

from pathlib import Path

from api.errors import artifact_not_found, artifact_path_invalid, state_not_found
from api.run_id_guard import validate_run_id
from docforge_core.domain.enums import ExportType
from docforge_core.io.run_paths import get_run_dir
from docforge_core.io.state_store import StateStore


class ArtifactService:
    def __init__(self, state_store: StateStore) -> None:
        self.state_store = state_store

    def resolve_download(self, artifact_id: str) -> Path:
        run_id, artifact_kind = parse_artifact_id(artifact_id)
        try:
            state = self.state_store.load_state(run_id)
        except FileNotFoundError as exc:
            raise state_not_found(run_id) from exc
        if artifact_kind not in {"final_docx", "risk_docx"}:
            raise artifact_not_found()
        if state.export_result is None or not state.export_result.docx_path:
            raise artifact_not_found()
        if artifact_kind == "final_docx" and state.export_result.export_type != ExportType.FINAL:
            raise artifact_not_found()
        if artifact_kind == "risk_docx" and state.export_result.export_type != ExportType.RISK:
            raise artifact_not_found()
        run_dir = get_run_dir(run_id, self.state_store.data_dir).resolve()
        candidate = (run_dir / state.export_result.docx_path).resolve()
        try:
            candidate.relative_to(run_dir)
        except ValueError as exc:
            raise artifact_path_invalid() from exc
        if not candidate.exists() or candidate.suffix.lower() != ".docx":
            raise artifact_not_found()
        return candidate


def parse_artifact_id(artifact_id: str) -> tuple[str, str]:
    if ":" not in artifact_id:
        raise artifact_not_found()
    run_id, artifact_kind = artifact_id.split(":", 1)
    validate_run_id(run_id)
    return run_id, artifact_kind
