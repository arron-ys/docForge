"""Persist run strategy settings and invalidate downstream strategy artifacts."""

from __future__ import annotations

import shutil
from typing import Literal

from docforge_core.domain.enums import ConfirmationStatus, NextAction, WorkflowStatus
from docforge_core.domain.schemas import DocForgeState, StateTransitionLog
from docforge_core.io.run_paths import get_run_dir
from docforge_core.io.state_store import StateStore

from .run_settings import set_run_settings

StrategyChangeMode = Literal["direct", "reevaluate", "restart"]


def strategy_change_mode(state: DocForgeState) -> StrategyChangeMode:
    if state.frozen_doc_plan is not None or _has_downstream_generation(state):
        return "restart"
    if state.workflow_status not in {
        WorkflowStatus.CREATED,
        WorkflowStatus.MATERIAL_UPLOADED,
    }:
        return "reevaluate"
    return "direct"


class StrategyResetService:
    """Apply settings changes without discarding sources or parsed evidence."""

    def __init__(self, state_store: StateStore) -> None:
        self.state_store = state_store

    def update_settings(
        self,
        run_id: str,
        settings: dict[str, str],
        *,
        allow_restart: bool = False,
    ) -> DocForgeState:
        state = self.state_store.load_state(run_id)
        mode = strategy_change_mode(state)
        if mode == "restart" and not allow_restart:
            raise StrategyRestartRequiredError

        set_run_settings(state, settings)
        if mode in {"reevaluate", "restart"}:
            self._reset_strategy(state)
        if mode == "restart":
            self._remove_downstream_artifacts(run_id)
        self.state_store.save_state(state)
        return state

    @staticmethod
    def _reset_strategy(state: DocForgeState) -> None:
        previous_status = state.workflow_status
        state.diagnosis_result = None
        state.template_strategy = None
        for confirmation in state.human_confirmations:
            if confirmation.status == ConfirmationStatus.PENDING:
                confirmation.status = ConfirmationStatus.REJECTED
            confirmation.metadata["invalidated_by_strategy_change"] = True
        state.pending_human_questions = []
        state.missing_information = []

        state.frozen_doc_plan = None
        state.outline = None
        state.section_plan = []
        state.screenshot_map = []
        state.plan_quality_gate_report = None
        state.plan_quality_gate_passed = False
        state.draft_versions = []
        state.current_draft_id = None
        state.current_draft_version = None
        state.figure_slots_ref = None
        state.figure_slots_result_id = None
        state.audit_report_ref = None
        state.audit_report_result_id = None
        state.draft_quality_gate_report_ref = None
        state.audit_reports = []
        state.draft_quality_gate_reports = []
        state.current_score = None
        state.blocker_issues = []
        state.major_issues = []
        state.minor_issues = []
        state.revision_round = 0
        state.export_result = None
        state.final_doc_path = None
        state.final_pdf_path = None
        state.risk_report_path = None

        if state.evidence_map:
            target_status = WorkflowStatus.EVIDENCE_MAPPED
            next_action = NextAction.DIAGNOSE_SOFTWARE_TYPE
        elif state.parsed_assets:
            target_status = WorkflowStatus.SOURCE_PARSED
            next_action = NextAction.ANALYZE_REFERENCE_STYLE
        elif state.source_registry:
            target_status = WorkflowStatus.MATERIAL_UPLOADED
            next_action = NextAction.PARSE_SOURCES
        else:
            target_status = WorkflowStatus.CREATED
            next_action = NextAction.INGEST_MATERIALS

        state.status_history.append(
            StateTransitionLog(
                from_status=previous_status,
                to_status=target_status,
                node_name="StrategyResetService.update_settings",
                reason="critical workspace strategy changed; downstream strategy invalidated",
            )
        )
        state.workflow_status = target_status
        state.next_action = next_action

    def _remove_downstream_artifacts(self, run_id: str) -> None:
        run_dir = get_run_dir(run_id, self.state_store.data_dir)
        for name in ("drafts", "audits", "exports"):
            directory = run_dir / name
            if directory.exists():
                shutil.rmtree(directory)
            directory.mkdir(parents=True, exist_ok=True)


class StrategyRestartRequiredError(RuntimeError):
    """Settings changes after plan freeze require explicit restart consent."""


def _has_downstream_generation(state: DocForgeState) -> bool:
    return bool(
        state.outline
        or state.section_plan
        or state.draft_versions
        or state.audit_reports
        or state.export_result
    )
