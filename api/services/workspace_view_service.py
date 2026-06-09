from __future__ import annotations

from api.errors import state_not_found
from api.schemas import WorkspaceView
from api.state_mapper import diagnostics_to_view, status_label, to_workspace_view
from docforge_core.io.state_store import StateStore
from docforge_core.workflow import WorkflowDiagnosticsService


class WorkspaceViewService:
    def __init__(self, state_store: StateStore) -> None:
        self.state_store = state_store

    def get_workspace(self, run_id: str) -> WorkspaceView:
        try:
            state = self.state_store.load_state(run_id)
        except FileNotFoundError as exc:
            raise state_not_found(run_id) from exc

        diagnostics = None
        try:
            report = WorkflowDiagnosticsService(self.state_store).inspect(run_id)
            diagnostics = diagnostics_to_view(report, status_label(state.workflow_status))
        except Exception:
            diagnostics = None
        return to_workspace_view(state, data_dir=self.state_store.data_dir, diagnostics=diagnostics)

