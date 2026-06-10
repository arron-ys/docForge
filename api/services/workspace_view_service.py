from __future__ import annotations

from api.errors import state_not_found
from api.schemas import CreateRunResponse, RunListItemView, RunListView, WorkspaceView
from api.state_mapper import (
    diagnostics_to_view,
    status_label,
    to_run_list_item_view,
    to_workspace_view,
)
from docforge_core.io.state_store import StateStore
from docforge_core.workflow import WorkflowDiagnosticsService


class WorkspaceViewService:
    def __init__(self, state_store: StateStore) -> None:
        self.state_store = state_store

    def list_runs(self) -> RunListView:
        runs_dir = self.state_store.data_dir / "runs"
        items: list[RunListItemView] = []
        if not runs_dir.exists():
            return RunListView(runs=[])

        for state_file in runs_dir.glob("*/state.json"):
            run_id = state_file.parent.name
            try:
                state = self.state_store.load_state(run_id)
            except Exception:
                continue
            items.append(to_run_list_item_view(state, state_file=state_file))

        return RunListView(
            runs=sorted(items, key=lambda item: item.updated_at, reverse=True)
        )

    def create_run(self, project_name: str | None = None) -> CreateRunResponse:
        state = self.state_store.create_initial_state(project_name=project_name)
        state_file = self.state_store.data_dir / "runs" / state.run_id / "state.json"
        return CreateRunResponse(
            run=to_run_list_item_view(state, state_file=state_file),
            workspace=self.get_workspace(state.run_id),
        )

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
