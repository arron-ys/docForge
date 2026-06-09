"""Sprint 12 orchestration for draft gate and controlled revisions."""

from __future__ import annotations

from docforge_core.agents.audit_agent import AuditAgentService
from docforge_core.agents.revision_agent import DraftRevisionAgent, RevisionResult
from docforge_core.domain.enums import NextAction, WorkflowStatus
from docforge_core.domain.schemas import DocForgeState, DraftAuditReport, DraftQualityGateReport
from docforge_core.gates.draft_quality_gate import DraftQualityGateService
from docforge_core.io.state_store import StateStore
from docforge_core.llm.base import LLMProvider


class RevisionLoopService:
    """Small Sprint12 coordinator with explicit one-step entrypoints."""

    def __init__(
        self,
        state_store: StateStore | None = None,
        llm_provider: LLMProvider | None = None,
    ) -> None:
        self.state_store = state_store or StateStore()
        self.llm_provider = llm_provider

    def run_quality_gate_for_current_draft(
        self,
        run_id: str,
    ) -> DraftQualityGateReport:
        return DraftQualityGateService(self.state_store).run(run_id)

    def revise_current_draft(self, run_id: str) -> RevisionResult:
        return DraftRevisionAgent(
            self.state_store,
            llm_provider=self.llm_provider,
        ).revise_current_draft(run_id)

    def audit_revised_draft(self, run_id: str) -> DraftAuditReport:
        state = self.state_store.load_state(run_id)
        if state.workflow_status == WorkflowStatus.DRAFT_V2_CREATED:
            version = 2
        elif state.workflow_status == WorkflowStatus.DRAFT_V3_CREATED:
            version = 3
        else:
            raise ValueError("audit_revised_draft 只接受 DRAFT_V2_CREATED 或 DRAFT_V3_CREATED")
        if state.next_action != NextAction.AUDIT_REVISED_DRAFT:
            raise ValueError("audit_revised_draft 要求 next_action 为 AUDIT_REVISED_DRAFT")
        return AuditAgentService(
            self.state_store,
            llm_provider=self.llm_provider,
        ).audit_draft(run_id, draft_version=version)

    def run_until_terminal_for_sprint12(self, run_id: str) -> DocForgeState:
        """Run at most v1 gate + two revision/audit/gate cycles."""
        for _ in range(7):
            state = self.state_store.load_state(run_id)
            if self._is_terminal(state):
                return state
            if state.next_action == NextAction.RUN_DRAFT_QUALITY_GATE:
                self.run_quality_gate_for_current_draft(run_id)
                continue
            if state.next_action == NextAction.REVISE_DRAFT:
                self.revise_current_draft(run_id)
                continue
            if state.next_action == NextAction.AUDIT_REVISED_DRAFT:
                self.audit_revised_draft(run_id)
                continue
            raise ValueError(f"Sprint12 不支持当前 next_action: {state.next_action}")
        state = self.state_store.load_state(run_id)
        if not self._is_terminal(state):
            raise ValueError("Sprint12 修订循环超过最大步数，fail closed")
        return state

    @staticmethod
    def _is_terminal(state: DocForgeState) -> bool:
        return (
            state.workflow_status == WorkflowStatus.DRAFT_QUALITY_GATE_PASSED
            and state.next_action == NextAction.EXPORT_DOCX
        ) or (
            state.workflow_status == WorkflowStatus.RISK_VERSION_READY
            and state.next_action == NextAction.EXPORT_RISK_DOCX
        )
