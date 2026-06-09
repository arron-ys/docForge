from __future__ import annotations

from api.action_guard import ActionGuard
from api.errors import action_not_allowed, state_not_found
from api.schemas import ActionResultView
from api.services.workspace_view_service import WorkspaceViewService
from docforge_core.io.state_store import StateStore
from docforge_core.workflow import WorkflowOrchestratorService


class RunActionService:
    def __init__(
        self,
        *,
        state_store: StateStore,
        orchestrator: WorkflowOrchestratorService,
        workspace_service: WorkspaceViewService,
    ) -> None:
        self.state_store = state_store
        self.orchestrator = orchestrator
        self.workspace_service = workspace_service
        self.guard = ActionGuard()

    def run_next(self, run_id: str) -> ActionResultView:
        return self._execute_guarded(run_id, "next", execute=True)

    def confirm_product_type(self, run_id: str) -> ActionResultView:
        return self._execute_guarded(run_id, "confirm-product-type", execute=False)

    def confirm_doc_plan(self, run_id: str) -> ActionResultView:
        return self._execute_guarded(run_id, "confirm-doc-plan", execute=False)

    def export_final_docx(self, run_id: str) -> ActionResultView:
        return self._execute_guarded(run_id, "export-final-docx", execute=True)

    def export_risk_docx(self, run_id: str) -> ActionResultView:
        return self._execute_guarded(run_id, "export-risk-docx", execute=True)

    def _execute_guarded(self, run_id: str, endpoint_action: str, *, execute: bool) -> ActionResultView:
        try:
            state = self.state_store.load_state(run_id)
        except FileNotFoundError as exc:
            raise state_not_found(run_id) from exc
        self.guard.ensure_allowed(state, endpoint_action)

        if not execute:
            raise action_not_allowed("该动作接口已预留，真实提交将在后续 Sprint 接入。")

        summary = self.orchestrator.run_next_step(run_id)
        if not summary.success:
            raise action_not_allowed(summary.error or "当前动作执行失败，状态未推进。")
        return ActionResultView(
            run_id=run_id,
            success=True,
            message=summary.description,
            workspace=self.workspace_service.get_workspace(run_id),
        )

