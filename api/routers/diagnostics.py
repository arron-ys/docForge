from __future__ import annotations

from fastapi import APIRouter, Depends

from api.deps import get_diagnostics_service, get_state_store
from api.errors import diagnostics_failed, state_not_found
from api.run_id_guard import validate_run_id
from api.schemas import DiagnosticSummaryView
from api.state_mapper import diagnostics_to_view, status_label
from docforge_core.io.state_store import StateStore
from docforge_core.workflow import WorkflowDiagnosticsService

router = APIRouter(tags=["diagnostics"])


@router.get("/runs/{run_id}/diagnostics", response_model=DiagnosticSummaryView)
def get_run_diagnostics(
    run_id: str,
    service: WorkflowDiagnosticsService = Depends(get_diagnostics_service),
    state_store: StateStore = Depends(get_state_store),
) -> DiagnosticSummaryView:
    validate_run_id(run_id)
    try:
        state = state_store.load_state(run_id)
    except FileNotFoundError as exc:
        raise state_not_found(run_id) from exc
    try:
        report = service.inspect(run_id)
    except Exception as exc:
        raise diagnostics_failed() from exc
    return diagnostics_to_view(report, status_label(state.workflow_status))
