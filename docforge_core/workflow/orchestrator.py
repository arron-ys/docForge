"""Thin, fail-closed workflow orchestrator for the existing DocForge services."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from docforge_core.domain.enums import NextAction, WorkflowStatus
from docforge_core.domain.schemas import DocForgeState, TemplateConfirmationDecision
from docforge_core.io.run_paths import get_run_dir, get_state_file
from docforge_core.io.state_store import StateStore

TERMINAL_STATES = {
    WorkflowStatus.FINAL_EXPORTED,
    WorkflowStatus.RISK_EXPORTED,
}
HUMAN_CONFIRMATION_STATES = {
    WorkflowStatus.USER_CONFIRM_REQUIRED,
}
RERUN_SAME_ACTIONS = {
    NextAction.ASK_HUMAN_CONFIRMATION,
    NextAction.STOP,
}
BUSINESS_ARTIFACT_DIRS = {"parsed", "evidence", "drafts", "audits", "exports"}


class WorkflowRecoverableError(RuntimeError):
    """Expected orchestration failure that leaves business state unadvanced."""


@dataclass(slots=True)
class WorkflowStepResult:
    """One orchestrator step outcome."""

    run_id: str
    action: str
    status_before: str
    status_after: str
    next_action_before: str
    next_action_after: str
    executed: bool
    success: bool
    description: str
    message: str = ""
    error: str | None = None
    waiting_for_human_confirmation: bool = False
    terminal: bool = False


@dataclass(slots=True)
class WorkflowRunSummary:
    """Compact summary returned by every public orchestrator entrypoint."""

    run_id: str
    workflow_status: str
    next_action: str
    description: str
    next_operation: str
    success: bool
    terminal: bool
    waiting_for_human_confirmation: bool
    executed_steps: int = 0
    last_step: WorkflowStepResult | None = None
    error: str | None = None
    docx_path: str | None = None


@dataclass(slots=True)
class WorkflowServiceRegistry:
    """Injected service objects/callables used by the orchestrator."""

    source_parsing_service: Any | None = None
    evidence_service: Any | None = None
    understanding_pipeline_service: Any | None = None
    human_confirm_gate: Any | None = None
    frozen_doc_plan_service: Any | None = None
    outline_agent: Any | None = None
    plan_quality_gate: Any | None = None
    writer_agent: Any | None = None
    figure_slot_planner: Any | None = None
    audit_agent: Any | None = None
    revision_loop_service: Any | None = None
    docx_export_service: Any | None = None
    evidence_indexer: Callable[[DocForgeState], Any] | None = None


@dataclass(frozen=True, slots=True)
class _StepDefinition:
    action: NextAction
    description: str
    service_attr: str | None
    method_name: str | None
    allowed_statuses: frozenset[WorkflowStatus]
    post_validator: Callable[[DocForgeState], bool]
    expected_artifact_refs: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class _ArtifactSnapshot:
    """Full pre-step snapshot for business artifact rollback."""

    run_dir: Path
    file_payloads: dict[Path, bytes]
    file_hashes: dict[Path, str]
    existing_files: set[Path]
    existing_dirs: set[Path]


class WorkflowOrchestratorService:
    """Route next_action to existing services with pre/post guards."""

    def __init__(
        self,
        state_store: StateStore | None = None,
        services: WorkflowServiceRegistry | None = None,
    ) -> None:
        self.state_store = state_store or StateStore()
        self.services = services or WorkflowServiceRegistry()

    def run_next_step(self, run_id: str) -> WorkflowRunSummary:
        """Run exactly one supported next_action, or stop without advancing."""
        state = self.state_store.load_state(run_id)
        if self._is_terminal(state):
            return self._summary(
                state,
                success=True,
                description="工作流已终止",
                next_operation="可下载 DOCX" if state.export_result else "无后续操作",
                terminal=True,
            )
        if self._is_waiting_for_human(state):
            return self._summary(
                state,
                success=True,
                description="等待人工确认模板方案",
                next_operation="请确认模板并冻结计划",
                waiting_for_human_confirmation=True,
            )

        before = self.state_store.load_state(run_id)
        definition = self._definition_for(before)
        if definition is None:
            return self._unsupported_summary(before)

        original_state_bytes: bytes | None = None
        artifact_snapshot: _ArtifactSnapshot | None = None
        try:
            self._pre_guard(before, definition)
            original_state_bytes = self._snapshot_state_file(run_id)
            artifact_snapshot = self._snapshot_business_artifacts_full(run_id)
            handler = self._resolve_handler(definition)
            handler(run_id)
            after = self.state_store.load_state(run_id)
            self._post_guard(before, after, definition, artifact_snapshot)
        except Exception as exc:
            error = self._restore_failed_step(
                run_id,
                original_state_bytes,
                artifact_snapshot,
                exc,
            )
            current = self._load_state_or(before)
            return self._summary(
                current,
                success=False,
                description=f"{definition.description} 失败",
                next_operation=self._describe_next_operation(current),
                error=error,
                last_step=self._step_result(
                    before,
                    current,
                    definition,
                    executed=False,
                    success=False,
                    error=error,
                ),
            )

        step = self._step_result(
            before,
            after,
            definition,
            executed=True,
            success=True,
            message=f"{definition.description} 已完成",
        )
        return self._summary(
            after,
            success=True,
            description=f"{definition.description} 已完成",
            next_operation=self._describe_next_operation(after),
            executed_steps=1,
            last_step=step,
            terminal=self._is_terminal(after),
            waiting_for_human_confirmation=self._is_waiting_for_human(after),
        )

    def get_summary(self, run_id: str) -> WorkflowRunSummary:
        """Return the current persisted workflow summary without executing services."""
        state = self.state_store.load_state(run_id)
        return self._summary(
            state,
            success=True,
            description="当前任务状态",
            next_operation=self._describe_next_operation(state),
        )

    def run_until_human_confirmation_required(
        self,
        run_id: str,
        max_steps: int = 30,
    ) -> WorkflowRunSummary:
        """Advance until the run reaches the human confirmation boundary."""
        return self._run_loop(
            run_id,
            max_steps=max_steps,
            stop_at_human_confirmation=True,
            stop_at_terminal=True,
        )

    def submit_human_confirmation(
        self,
        run_id: str,
        decision: TemplateConfirmationDecision,
    ) -> WorkflowRunSummary:
        """Submit a real human decision and freeze the plan through existing services."""
        before = self.state_store.load_state(run_id)
        if not (
            before.workflow_status == WorkflowStatus.USER_CONFIRM_REQUIRED
            and before.next_action == NextAction.ASK_HUMAN_CONFIRMATION
        ):
            return self._summary(
                before,
                success=False,
                description="人工确认提交失败",
                next_operation=self._describe_next_operation(before),
                error="当前状态不允许提交模板确认",
            )

        definition = _StepDefinition(
            action=NextAction.FREEZE_DOC_PLAN,
            description="确认模板并冻结计划",
            service_attr=None,
            method_name=None,
            allowed_statuses=frozenset({WorkflowStatus.USER_CONFIRM_REQUIRED}),
            post_validator=lambda state: (
                state.workflow_status == WorkflowStatus.PLAN_FROZEN
                and state.next_action == NextAction.CREATE_OUTLINE
                and state.frozen_doc_plan is not None
            ),
        )
        original_state_bytes: bytes | None = None
        artifact_snapshot: _ArtifactSnapshot | None = None
        try:
            self._pre_guard(before, definition)
            original_state_bytes = self._snapshot_state_file(run_id)
            artifact_snapshot = self._snapshot_business_artifacts_full(run_id)
            gate = self._required_service("human_confirm_gate")
            freezer = self._required_service("frozen_doc_plan_service")
            gate.confirm_template_strategy(run_id, decision)
            freezer.freeze_confirmed_plan(run_id)
            after = self.state_store.load_state(run_id)
            self._post_guard(before, after, definition, artifact_snapshot)
        except Exception as exc:
            error = self._restore_failed_step(
                run_id,
                original_state_bytes,
                artifact_snapshot,
                exc,
            )
            current = self._load_state_or(before)
            return self._summary(
                current,
                success=False,
                description="人工确认提交失败",
                next_operation=self._describe_next_operation(current),
                error=error,
                last_step=self._step_result(
                    before,
                    current,
                    definition,
                    executed=False,
                    success=False,
                    error=error,
                ),
            )

        step = self._step_result(
            before,
            after,
            definition,
            executed=True,
            success=True,
            message="模板已确认，FrozenDocPlan 已冻结",
        )
        return self._summary(
            after,
            success=True,
            description="模板已确认，FrozenDocPlan 已冻结",
            next_operation=self._describe_next_operation(after),
            executed_steps=1,
            last_step=step,
        )

    def run_until_terminal(
        self,
        run_id: str,
        max_steps: int = 50,
    ) -> WorkflowRunSummary:
        """Run until FINAL_EXPORTED/RISK_EXPORTED or a guarded stop is reached."""
        return self._run_loop(
            run_id,
            max_steps=max_steps,
            stop_at_human_confirmation=True,
            stop_at_terminal=True,
        )

    def resume(self, run_id: str) -> WorkflowRunSummary:
        """Resume from the persisted state using the normal terminal loop."""
        return self.run_until_terminal(run_id)

    def _run_loop(
        self,
        run_id: str,
        *,
        max_steps: int,
        stop_at_human_confirmation: bool,
        stop_at_terminal: bool,
    ) -> WorkflowRunSummary:
        executed_steps = 0
        last_step: WorkflowStepResult | None = None
        state = self.state_store.load_state(run_id)
        if max_steps <= 0:
            return self._summary(
                state,
                success=False,
                description="执行失败",
                next_operation=self._describe_next_operation(state),
                error="max_steps 必须大于 0",
            )

        for _ in range(max_steps):
            state = self.state_store.load_state(run_id)
            if stop_at_terminal and self._is_terminal(state):
                return self._summary(
                    state,
                    success=True,
                    description="工作流已终止",
                    next_operation="可下载 DOCX" if state.export_result else "无后续操作",
                    executed_steps=executed_steps,
                    last_step=last_step,
                    terminal=True,
                )
            if stop_at_human_confirmation and self._is_waiting_for_human(state):
                return self._summary(
                    state,
                    success=True,
                    description="已到达人工确认点",
                    next_operation="请确认模板并冻结计划",
                    executed_steps=executed_steps,
                    last_step=last_step,
                    waiting_for_human_confirmation=True,
                )

            summary = self.run_next_step(run_id)
            if summary.last_step is not None:
                last_step = summary.last_step
            if summary.executed_steps:
                executed_steps += summary.executed_steps
            if not summary.success or summary.terminal or summary.waiting_for_human_confirmation:
                state = self.state_store.load_state(run_id)
                return self._summary(
                    state,
                    success=summary.success,
                    description=summary.description,
                    next_operation=summary.next_operation,
                    executed_steps=executed_steps,
                    last_step=last_step,
                    error=summary.error,
                    terminal=summary.terminal,
                    waiting_for_human_confirmation=summary.waiting_for_human_confirmation,
                )
            if summary.last_step is None or not summary.last_step.executed:
                break

        state = self.state_store.load_state(run_id)
        terminal = self._is_terminal(state)
        waiting = self._is_waiting_for_human(state)
        return self._summary(
            state,
            success=terminal or waiting,
            description=(
                "工作流已终止"
                if terminal
                else "已到达人工确认点"
                if waiting
                else "执行达到 max_steps，fail closed"
            ),
            next_operation=self._describe_next_operation(state),
            executed_steps=executed_steps,
            last_step=last_step,
            error=None if terminal or waiting else "执行达到 max_steps，fail closed",
            terminal=terminal,
            waiting_for_human_confirmation=waiting,
        )

    def _definition_for(self, state: DocForgeState) -> _StepDefinition | None:
        definitions = self._definitions()
        if (
            state.next_action == NextAction.ANALYZE_REFERENCE_STYLE
            and state.workflow_status == WorkflowStatus.SOURCE_PARSED
        ):
            return definitions[NextAction.EXTRACT_EVIDENCE]
        if (
            state.next_action == NextAction.DIAGNOSE_SOFTWARE_TYPE
            and state.workflow_status == WorkflowStatus.EVIDENCE_MAPPED
        ):
            return definitions[NextAction.DIAGNOSE_SOFTWARE_TYPE]
        return definitions.get(state.next_action)

    def _definitions(self) -> dict[NextAction, _StepDefinition]:
        return {
            NextAction.PARSE_SOURCES: _StepDefinition(
                action=NextAction.PARSE_SOURCES,
                description="解析资料",
                service_attr="source_parsing_service",
                method_name="parse_run",
                allowed_statuses=frozenset({WorkflowStatus.MATERIAL_UPLOADED}),
                post_validator=lambda state: (
                    state.workflow_status in {
                        WorkflowStatus.SOURCE_PARSED,
                        WorkflowStatus.MATERIAL_UPLOADED,
                    }
                    and state.next_action
                    in {NextAction.ANALYZE_REFERENCE_STYLE, NextAction.PARSE_SOURCES}
                ),
            ),
            NextAction.EXTRACT_EVIDENCE: _StepDefinition(
                action=NextAction.EXTRACT_EVIDENCE,
                description="生成 Evidence",
                service_attr="evidence_service",
                method_name="extract_run",
                allowed_statuses=frozenset({WorkflowStatus.SOURCE_PARSED}),
                post_validator=lambda state: (
                    state.workflow_status == WorkflowStatus.EVIDENCE_MAPPED
                    and state.next_action == NextAction.DIAGNOSE_SOFTWARE_TYPE
                    and bool(state.evidence_map)
                ),
            ),
            NextAction.DIAGNOSE_SOFTWARE_TYPE: _StepDefinition(
                action=NextAction.DIAGNOSE_SOFTWARE_TYPE,
                description="理解产品并推荐模板",
                service_attr="understanding_pipeline_service",
                method_name="run_until_template_recommended",
                allowed_statuses=frozenset({WorkflowStatus.EVIDENCE_MAPPED}),
                post_validator=lambda state: (
                    state.workflow_status == WorkflowStatus.TEMPLATE_RECOMMENDED
                    and state.next_action == NextAction.ASK_HUMAN_CONFIRMATION
                    and state.template_strategy is not None
                    and state.diagnosis_result is not None
                ),
            ),
            NextAction.ASK_HUMAN_CONFIRMATION: _StepDefinition(
                action=NextAction.ASK_HUMAN_CONFIRMATION,
                description="准备人工确认",
                service_attr="human_confirm_gate",
                method_name="prepare_confirmation",
                allowed_statuses=frozenset({WorkflowStatus.TEMPLATE_RECOMMENDED}),
                post_validator=lambda state: (
                    state.workflow_status == WorkflowStatus.USER_CONFIRM_REQUIRED
                    and state.next_action == NextAction.ASK_HUMAN_CONFIRMATION
                ),
            ),
            NextAction.FREEZE_DOC_PLAN: _StepDefinition(
                action=NextAction.FREEZE_DOC_PLAN,
                description="冻结文档计划",
                service_attr="frozen_doc_plan_service",
                method_name="freeze_confirmed_plan",
                allowed_statuses=frozenset({WorkflowStatus.USER_CONFIRMED}),
                post_validator=lambda state: (
                    state.workflow_status == WorkflowStatus.PLAN_FROZEN
                    and state.next_action == NextAction.CREATE_OUTLINE
                    and state.frozen_doc_plan is not None
                ),
            ),
            NextAction.CREATE_OUTLINE: _StepDefinition(
                action=NextAction.CREATE_OUTLINE,
                description="生成大纲和 SectionPlan",
                service_attr="outline_agent",
                method_name="create_outline",
                allowed_statuses=frozenset({WorkflowStatus.PLAN_FROZEN}),
                post_validator=lambda state: (
                    state.workflow_status == WorkflowStatus.OUTLINE_CREATED
                    and state.next_action == NextAction.RUN_PLAN_QUALITY_GATE
                    and state.outline is not None
                    and bool(state.section_plan)
                ),
            ),
            NextAction.RUN_PLAN_QUALITY_GATE: _StepDefinition(
                action=NextAction.RUN_PLAN_QUALITY_GATE,
                description="运行 PlanQualityGate",
                service_attr="plan_quality_gate",
                method_name="run",
                allowed_statuses=frozenset({WorkflowStatus.OUTLINE_CREATED}),
                post_validator=lambda state: (
                    state.workflow_status
                    in {WorkflowStatus.PLAN_GATE_PASSED, WorkflowStatus.PLAN_GATE_FAILED}
                    and state.next_action
                    in {NextAction.WRITE_DRAFT, NextAction.ASK_MISSING_INFORMATION}
                    and state.plan_quality_gate_report is not None
                ),
            ),
            NextAction.WRITE_DRAFT: _StepDefinition(
                action=NextAction.WRITE_DRAFT,
                description="生成 v1 草稿",
                service_attr="writer_agent",
                method_name="write_v1_draft",
                allowed_statuses=frozenset({WorkflowStatus.PLAN_GATE_PASSED}),
                post_validator=lambda state: (
                    state.workflow_status == WorkflowStatus.DRAFT_V1_CREATED
                    and state.next_action == NextAction.PLAN_FIGURE_SLOTS
                    and state.current_draft_version == "v1"
                ),
                expected_artifact_refs=("drafts/draft_v1.json",),
            ),
            NextAction.PLAN_FIGURE_SLOTS: _StepDefinition(
                action=NextAction.PLAN_FIGURE_SLOTS,
                description="生成配图补图清单",
                service_attr="figure_slot_planner",
                method_name="plan_figure_slots",
                allowed_statuses=frozenset({WorkflowStatus.DRAFT_V1_CREATED}),
                post_validator=lambda state: (
                    state.workflow_status == WorkflowStatus.FIGURE_SLOTS_PLANNED
                    and state.next_action == NextAction.AUDIT_DRAFT
                    and state.figure_slots_ref == "drafts/figure_slots_v1.json"
                ),
                expected_artifact_refs=("figure_slots_ref",),
            ),
            NextAction.AUDIT_DRAFT: _StepDefinition(
                action=NextAction.AUDIT_DRAFT,
                description="审计 v1 草稿",
                service_attr="audit_agent",
                method_name="audit_draft",
                allowed_statuses=frozenset(
                    {WorkflowStatus.FIGURE_SLOTS_PLANNED, WorkflowStatus.DRAFT_V1_CREATED}
                ),
                post_validator=lambda state: (
                    state.workflow_status == WorkflowStatus.DRAFT_AUDITED
                    and state.next_action == NextAction.RUN_DRAFT_QUALITY_GATE
                    and state.audit_report_ref == "drafts/audit_report_v1.json"
                ),
                expected_artifact_refs=("audit_report_ref",),
            ),
            NextAction.RUN_DRAFT_QUALITY_GATE: _StepDefinition(
                action=NextAction.RUN_DRAFT_QUALITY_GATE,
                description="运行 DraftQualityGate",
                service_attr="revision_loop_service",
                method_name="run_quality_gate_for_current_draft",
                allowed_statuses=frozenset(
                    {
                        WorkflowStatus.DRAFT_AUDITED,
                        WorkflowStatus.DRAFT_V2_AUDITED,
                        WorkflowStatus.AUDIT_V2_COMPLETED,
                        WorkflowStatus.DRAFT_V3_AUDITED,
                        WorkflowStatus.AUDIT_V3_COMPLETED,
                    }
                ),
                post_validator=lambda state: (
                    state.workflow_status
                    in {
                        WorkflowStatus.DRAFT_QUALITY_GATE_PASSED,
                        WorkflowStatus.DRAFT_REVISION_REQUIRED,
                        WorkflowStatus.RISK_VERSION_READY,
                    }
                    and state.next_action
                    in {
                        NextAction.EXPORT_DOCX,
                        NextAction.REVISE_DRAFT,
                        NextAction.EXPORT_RISK_DOCX,
                    }
                    and state.draft_quality_gate_report_ref is not None
                ),
                expected_artifact_refs=("draft_quality_gate_report_ref",),
            ),
            NextAction.REVISE_DRAFT: _StepDefinition(
                action=NextAction.REVISE_DRAFT,
                description="执行受控修订",
                service_attr="revision_loop_service",
                method_name="revise_current_draft",
                allowed_statuses=frozenset({WorkflowStatus.DRAFT_REVISION_REQUIRED}),
                post_validator=lambda state: (
                    state.workflow_status
                    in {WorkflowStatus.DRAFT_V2_CREATED, WorkflowStatus.DRAFT_V3_CREATED}
                    and state.next_action == NextAction.AUDIT_REVISED_DRAFT
                    and state.current_draft_version in {"v2", "v3"}
                ),
            ),
            NextAction.AUDIT_REVISED_DRAFT: _StepDefinition(
                action=NextAction.AUDIT_REVISED_DRAFT,
                description="审计修订稿",
                service_attr="revision_loop_service",
                method_name="audit_revised_draft",
                allowed_statuses=frozenset(
                    {WorkflowStatus.DRAFT_V2_CREATED, WorkflowStatus.DRAFT_V3_CREATED}
                ),
                post_validator=lambda state: (
                    state.workflow_status
                    in {WorkflowStatus.DRAFT_V2_AUDITED, WorkflowStatus.DRAFT_V3_AUDITED}
                    and state.next_action == NextAction.RUN_DRAFT_QUALITY_GATE
                    and state.audit_report_ref
                    in {"drafts/audit_report_v2.json", "drafts/audit_report_v3.json"}
                ),
                expected_artifact_refs=("audit_report_ref",),
            ),
            NextAction.EXPORT_DOCX: _StepDefinition(
                action=NextAction.EXPORT_DOCX,
                description="导出 DOCX",
                service_attr="docx_export_service",
                method_name="export_current_docx",
                allowed_statuses=frozenset({WorkflowStatus.DRAFT_QUALITY_GATE_PASSED}),
                post_validator=lambda state: (
                    state.workflow_status == WorkflowStatus.FINAL_EXPORTED
                    and state.next_action == NextAction.STOP
                    and state.export_result is not None
                    and state.export_result.docx_path is not None
                    and state.export_result.pdf_path is None
                    and state.final_pdf_path is None
                ),
                expected_artifact_refs=("export_result.docx_path",),
            ),
            NextAction.EXPORT_RISK_DOCX: _StepDefinition(
                action=NextAction.EXPORT_RISK_DOCX,
                description="导出风险版 DOCX",
                service_attr="docx_export_service",
                method_name="export_current_docx",
                allowed_statuses=frozenset({WorkflowStatus.RISK_VERSION_READY}),
                post_validator=lambda state: (
                    state.workflow_status == WorkflowStatus.RISK_EXPORTED
                    and state.next_action == NextAction.STOP
                    and state.export_result is not None
                    and state.export_result.docx_path is not None
                    and state.export_result.pdf_path is None
                    and state.final_pdf_path is None
                ),
                expected_artifact_refs=("export_result.docx_path",),
            ),
            NextAction.STOP: _StepDefinition(
                action=NextAction.STOP,
                description="停止",
                service_attr=None,
                method_name=None,
                allowed_statuses=frozenset(TERMINAL_STATES),
                post_validator=lambda state: self._is_terminal(state),
            ),
        }

    def _pre_guard(
        self,
        state: DocForgeState,
        definition: _StepDefinition,
    ) -> None:
        if state.workflow_status not in definition.allowed_statuses:
            raise WorkflowRecoverableError(
                f"{definition.action.value} 不支持当前 workflow_status={state.workflow_status.value}"
            )
        if (
            state.next_action != definition.action
            and not (
                state.next_action == NextAction.ANALYZE_REFERENCE_STYLE
                and definition.action == NextAction.EXTRACT_EVIDENCE
                and state.workflow_status == WorkflowStatus.SOURCE_PARSED
            )
            and not (
                state.next_action == NextAction.ASK_HUMAN_CONFIRMATION
                and definition.action == NextAction.FREEZE_DOC_PLAN
                and state.workflow_status == WorkflowStatus.USER_CONFIRM_REQUIRED
            )
        ):
            raise WorkflowRecoverableError(
                f"state.next_action={state.next_action.value} 与 handler={definition.action.value} 不一致"
            )
        if (
            self._is_waiting_for_human(state)
            and definition.action
            not in {NextAction.ASK_HUMAN_CONFIRMATION, NextAction.FREEZE_DOC_PLAN}
        ):
            raise WorkflowRecoverableError("当前等待人工确认，不允许自动推进")
        self._validate_state_refs_exist(state)
        self._validate_no_unclaimed_artifacts(state)

    def _post_guard(
        self,
        before: DocForgeState,
        after: DocForgeState,
        definition: _StepDefinition,
        before_snapshot: _ArtifactSnapshot,
    ) -> None:
        if after.run_id != before.run_id:
            raise WorkflowRecoverableError("服务返回后 run_id 发生变化")
        if not definition.post_validator(after):
            raise WorkflowRecoverableError(
                f"{definition.action.value} 后置状态校验失败: "
                f"{after.workflow_status.value}/{after.next_action.value}"
            )
        if after.next_action == before.next_action and definition.action not in RERUN_SAME_ACTIONS:
            raise WorkflowRecoverableError("服务执行后 next_action 未推进，fail closed")
        self._validate_state_refs_exist(after)
        self._validate_expected_artifacts(after, definition.expected_artifact_refs)
        self._validate_existing_artifacts_unchanged(
            run_id=before.run_id,
            before=before_snapshot.file_hashes,
        )
        if after.export_result is not None:
            if after.export_result.pdf_path or after.final_pdf_path:
                raise WorkflowRecoverableError("当前工作流不允许导出 PDF")
            if after.risk_report_path or after.export_result.risk_report_path:
                raise WorkflowRecoverableError("当前工作流不允许单独导出风险报告")

    def _resolve_handler(self, definition: _StepDefinition) -> Callable[[str], Any]:
        if definition.service_attr is None or definition.method_name is None:
            return lambda _run_id: None
        service = self._required_service(definition.service_attr)
        handler = getattr(service, definition.method_name, None)
        if handler is None or not callable(handler):
            raise WorkflowRecoverableError(
                f"服务 {definition.service_attr} 缺少方法 {definition.method_name}"
            )

        def _handler(run_id: str) -> Any:
            result = handler(run_id)
            if definition.action == NextAction.EXTRACT_EVIDENCE and self.services.evidence_indexer:
                state = self.state_store.load_state(run_id)
                self.services.evidence_indexer(state)
            return result

        return _handler

    def _required_service(self, attr_name: str) -> Any:
        service = getattr(self.services, attr_name)
        if service is None:
            raise WorkflowRecoverableError(f"缺少工作流服务依赖: {attr_name}")
        return service

    def _validate_state_refs_exist(self, state: DocForgeState) -> None:
        run_dir = get_run_dir(state.run_id, self.state_store.data_dir)
        refs = [
            *[
                item.content_ref
                for item in state.draft_versions
                if item.content_ref
            ],
            state.figure_slots_ref,
            state.audit_report_ref,
            state.draft_quality_gate_report_ref,
            state.final_doc_path,
            state.export_result.docx_path
            if state.export_result is not None
            else None,
        ]
        for ref in refs:
            if not ref:
                continue
            path = self._safe_run_ref(run_dir, ref)
            if not path.exists():
                raise WorkflowRecoverableError(f"state 指向的产物不存在: {ref}")

    def _validate_expected_artifacts(
        self,
        state: DocForgeState,
        refs: tuple[str, ...],
    ) -> None:
        run_dir = get_run_dir(state.run_id, self.state_store.data_dir)
        for ref in refs:
            resolved = ref if "/" in ref else self._resolve_state_ref_value(state, ref)
            if not resolved:
                raise WorkflowRecoverableError(f"缺少预期产物引用: {ref}")
            if not self._safe_run_ref(run_dir, str(resolved)).exists():
                raise WorkflowRecoverableError(f"预期产物文件不存在: {resolved}")

    def _validate_no_unclaimed_artifacts(self, state: DocForgeState) -> None:
        run_dir = get_run_dir(state.run_id, self.state_store.data_dir)
        evidence_map = run_dir / "evidence" / "evidence_map.json"
        if (
            state.workflow_status == WorkflowStatus.SOURCE_PARSED
            and state.next_action
            in {NextAction.ANALYZE_REFERENCE_STYLE, NextAction.EXTRACT_EVIDENCE}
            and evidence_map.exists()
            and not state.evidence_map
        ):
            raise WorkflowRecoverableError("存在未被 state 承认的 stale evidence_map.json")
        draft_v1 = run_dir / "drafts" / "draft_v1.json"
        if (
            state.workflow_status == WorkflowStatus.PLAN_GATE_PASSED
            and state.next_action == NextAction.WRITE_DRAFT
            and draft_v1.exists()
            and not any(item.content_ref == "drafts/draft_v1.json" for item in state.draft_versions)
        ):
            raise WorkflowRecoverableError("存在未被 state 承认的 stale draft_v1.json")
        figure = run_dir / "drafts" / "figure_slots_v1.json"
        if (
            state.workflow_status == WorkflowStatus.DRAFT_V1_CREATED
            and state.next_action == NextAction.PLAN_FIGURE_SLOTS
            and figure.exists()
            and state.figure_slots_ref != "drafts/figure_slots_v1.json"
        ):
            raise WorkflowRecoverableError("存在未被 state 承认的 stale figure_slots_v1.json")
        audit_target_version = self._target_audit_version(state)
        if audit_target_version is not None:
            audit = run_dir / "drafts" / f"audit_report_v{audit_target_version}.json"
            if (
                audit.exists()
                and state.audit_report_ref
                != f"drafts/audit_report_v{audit_target_version}.json"
            ):
                raise WorkflowRecoverableError(
                    f"存在未被 state 承认的 stale audit_report_v{audit_target_version}.json"
                )
        gate_target_version = self._target_quality_gate_version(state)
        if gate_target_version is not None:
            quality = run_dir / "drafts" / f"quality_gate_report_v{gate_target_version}.json"
            if (
                quality.exists()
                and state.draft_quality_gate_report_ref
                != f"drafts/quality_gate_report_v{gate_target_version}.json"
            ):
                raise WorkflowRecoverableError(
                    f"存在未被 state 承认的 stale quality_gate_report_v{gate_target_version}.json"
                )

    @staticmethod
    def _target_audit_version(state: DocForgeState) -> int | None:
        if state.next_action == NextAction.AUDIT_DRAFT:
            return 1
        if state.next_action == NextAction.AUDIT_REVISED_DRAFT:
            if state.current_draft_version in {"v2", "v3"}:
                return int(state.current_draft_version[1])
            if state.workflow_status == WorkflowStatus.DRAFT_V2_CREATED:
                return 2
            if state.workflow_status == WorkflowStatus.DRAFT_V3_CREATED:
                return 3
        return None

    @staticmethod
    def _target_quality_gate_version(state: DocForgeState) -> int | None:
        if state.next_action != NextAction.RUN_DRAFT_QUALITY_GATE:
            return None
        if state.current_draft_version in {"v1", "v2", "v3"}:
            return int(state.current_draft_version[1])
        if state.workflow_status in {WorkflowStatus.DRAFT_AUDITED, WorkflowStatus.AUDIT_V1_COMPLETED}:
            return 1
        if state.workflow_status in {WorkflowStatus.DRAFT_V2_AUDITED, WorkflowStatus.AUDIT_V2_COMPLETED}:
            return 2
        if state.workflow_status in {WorkflowStatus.DRAFT_V3_AUDITED, WorkflowStatus.AUDIT_V3_COMPLETED}:
            return 3
        return None

    def _snapshot_business_artifacts_full(self, run_id: str) -> _ArtifactSnapshot:
        run_dir = get_run_dir(run_id, self.state_store.data_dir)
        file_payloads: dict[Path, bytes] = {}
        file_hashes: dict[Path, str] = {}
        existing_files: set[Path] = set()
        existing_dirs: set[Path] = set()
        if not run_dir.exists():
            return _ArtifactSnapshot(
                run_dir=run_dir,
                file_payloads=file_payloads,
                file_hashes=file_hashes,
                existing_files=existing_files,
                existing_dirs=existing_dirs,
            )
        for dirname in BUSINESS_ARTIFACT_DIRS:
            directory = run_dir / dirname
            if not directory.exists():
                continue
            existing_dirs.add(directory)
            for path in sorted(directory.rglob("*")):
                if path.is_dir():
                    existing_dirs.add(path)
                    continue
                if path.is_file():
                    payload = path.read_bytes()
                    file_payloads[path] = payload
                    file_hashes[path] = hashlib.sha256(payload).hexdigest()
                    existing_files.add(path)
        return _ArtifactSnapshot(
            run_dir=run_dir,
            file_payloads=file_payloads,
            file_hashes=file_hashes,
            existing_files=existing_files,
            existing_dirs=existing_dirs,
        )

    def _snapshot_state_file(self, run_id: str) -> bytes:
        return get_state_file(run_id, self.state_store.data_dir).read_bytes()

    def _restore_state_file(self, run_id: str, payload: bytes) -> None:
        state_file = get_state_file(run_id, self.state_store.data_dir)
        rollback = state_file.with_suffix(".json.orchestrator_rollback.tmp")
        try:
            rollback.write_bytes(payload)
            rollback.replace(state_file)
        finally:
            if rollback.exists():
                rollback.unlink()

    def _restore_failed_step(
        self,
        run_id: str,
        state_payload: bytes | None,
        artifact_snapshot: _ArtifactSnapshot | None,
        original_error: Exception,
    ) -> str:
        restore_errors: list[str] = []
        if artifact_snapshot is not None:
            try:
                self._restore_business_artifacts(run_id, artifact_snapshot)
            except Exception as exc:
                restore_errors.append(f"artifact restore failed: {exc}")
        if state_payload is not None:
            try:
                self._restore_state_file(run_id, state_payload)
            except Exception as exc:
                restore_errors.append(f"state restore failed: {exc}")
        if restore_errors:
            return f"{original_error}; rollback failed: {'; '.join(restore_errors)}"
        return str(original_error)

    def _restore_business_artifacts(
        self,
        run_id: str,
        snapshot: _ArtifactSnapshot,
    ) -> None:
        run_dir = get_run_dir(run_id, self.state_store.data_dir)
        current_files = set(self._iter_business_artifact_files(run_dir))
        for path in current_files - snapshot.existing_files:
            path.unlink()
        for path, payload in snapshot.file_payloads.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            if not path.exists() or path.read_bytes() != payload:
                path.write_bytes(payload)
        self._cleanup_new_empty_dirs(run_dir, snapshot)

    def _cleanup_new_empty_dirs(
        self,
        run_dir: Path,
        snapshot: _ArtifactSnapshot,
    ) -> None:
        directories = sorted(
            self._iter_business_artifact_dirs(run_dir),
            key=lambda path: len(path.parts),
            reverse=True,
        )
        for path in directories:
            if path in snapshot.existing_dirs or path == run_dir:
                continue
            try:
                path.rmdir()
            except OSError:
                continue

    @staticmethod
    def _iter_business_artifact_files(run_dir: Path) -> list[Path]:
        files: list[Path] = []
        for dirname in BUSINESS_ARTIFACT_DIRS:
            directory = run_dir / dirname
            if not directory.exists():
                continue
            files.extend(path for path in directory.rglob("*") if path.is_file())
        return files

    @staticmethod
    def _iter_business_artifact_dirs(run_dir: Path) -> list[Path]:
        directories: list[Path] = []
        for dirname in BUSINESS_ARTIFACT_DIRS:
            directory = run_dir / dirname
            if not directory.exists():
                continue
            directories.append(directory)
            directories.extend(path for path in directory.rglob("*") if path.is_dir())
        return directories

    def _validate_existing_artifacts_unchanged(
        self,
        *,
        run_id: str,
        before: dict[Path, str],
    ) -> None:
        for path, digest in before.items():
            if not path.exists():
                run_dir = get_run_dir(run_id, self.state_store.data_dir)
                try:
                    ref = str(path.relative_to(run_dir))
                except ValueError:
                    ref = str(path)
                raise WorkflowRecoverableError(f"已有产物被删除: {ref}")
            if self._sha256(path) != digest:
                run_dir = get_run_dir(run_id, self.state_store.data_dir)
                try:
                    ref = str(path.relative_to(run_dir))
                except ValueError:
                    ref = str(path)
                raise WorkflowRecoverableError(f"已有产物被改写: {ref}")

    def _unsupported_summary(self, state: DocForgeState) -> WorkflowRunSummary:
        return self._summary(
            state,
            success=False,
            description="当前 next_action 尚未接入 Orchestrator",
            next_operation=self._describe_next_operation(state),
            error=f"unsupported next_action: {state.next_action.value}",
        )

    def _step_result(
        self,
        before: DocForgeState,
        after: DocForgeState,
        definition: _StepDefinition,
        *,
        executed: bool,
        success: bool,
        message: str = "",
        error: str | None = None,
    ) -> WorkflowStepResult:
        return WorkflowStepResult(
            run_id=before.run_id,
            action=definition.action.value,
            status_before=before.workflow_status.value,
            status_after=after.workflow_status.value,
            next_action_before=before.next_action.value,
            next_action_after=after.next_action.value,
            executed=executed,
            success=success,
            description=definition.description,
            message=message,
            error=error,
            waiting_for_human_confirmation=self._is_waiting_for_human(after),
            terminal=self._is_terminal(after),
        )

    def _summary(
        self,
        state: DocForgeState,
        *,
        success: bool,
        description: str,
        next_operation: str,
        executed_steps: int = 0,
        last_step: WorkflowStepResult | None = None,
        error: str | None = None,
        terminal: bool | None = None,
        waiting_for_human_confirmation: bool | None = None,
    ) -> WorkflowRunSummary:
        return WorkflowRunSummary(
            run_id=state.run_id,
            workflow_status=state.workflow_status.value,
            next_action=state.next_action.value,
            description=description,
            next_operation=next_operation,
            success=success,
            terminal=self._is_terminal(state) if terminal is None else terminal,
            waiting_for_human_confirmation=(
                self._is_waiting_for_human(state)
                if waiting_for_human_confirmation is None
                else waiting_for_human_confirmation
            ),
            executed_steps=executed_steps,
            last_step=last_step,
            error=error,
            docx_path=state.export_result.docx_path
            if state.export_result is not None
            else state.final_doc_path,
        )

    def _describe_next_operation(self, state: DocForgeState) -> str:
        if self._is_terminal(state):
            return "可下载 DOCX" if state.export_result else "无后续操作"
        if self._is_waiting_for_human(state):
            return "请确认模板并冻结计划"
        mapping = {
            NextAction.INGEST_MATERIALS: "请上传参考资料和自有产品资料",
            NextAction.PARSE_SOURCES: "解析资料",
            NextAction.ANALYZE_REFERENCE_STYLE: "生成 Evidence",
            NextAction.EXTRACT_EVIDENCE: "生成 Evidence",
            NextAction.DIAGNOSE_SOFTWARE_TYPE: "理解产品并推荐模板",
            NextAction.FREEZE_DOC_PLAN: "冻结文档计划",
            NextAction.CREATE_OUTLINE: "生成大纲和 SectionPlan",
            NextAction.RUN_PLAN_QUALITY_GATE: "运行 PlanQualityGate",
            NextAction.ASK_MISSING_INFORMATION: "等待补充缺失信息",
            NextAction.WRITE_DRAFT: "生成 v1 草稿",
            NextAction.PLAN_FIGURE_SLOTS: "生成配图补图清单",
            NextAction.AUDIT_DRAFT: "审计 v1 草稿",
            NextAction.RUN_DRAFT_QUALITY_GATE: "运行 DraftQualityGate",
            NextAction.REVISE_DRAFT: "执行受控修订",
            NextAction.AUDIT_REVISED_DRAFT: "审计修订稿",
            NextAction.EXPORT_DOCX: "导出 DOCX",
            NextAction.EXPORT_RISK_DOCX: "导出风险版 DOCX",
            NextAction.STOP: "无后续操作",
        }
        return mapping.get(state.next_action, f"未支持动作: {state.next_action.value}")

    def _is_waiting_for_human(self, state: DocForgeState) -> bool:
        return (
            state.next_action == NextAction.ASK_HUMAN_CONFIRMATION
            and state.workflow_status in HUMAN_CONFIRMATION_STATES
        )

    @staticmethod
    def _is_terminal(state: DocForgeState) -> bool:
        return state.workflow_status in TERMINAL_STATES and state.next_action == NextAction.STOP

    def _load_state_or(self, fallback: DocForgeState) -> DocForgeState:
        try:
            return self.state_store.load_state(fallback.run_id)
        except Exception:
            return fallback

    @staticmethod
    def _sha256(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    @staticmethod
    def _resolve_state_ref_value(state: DocForgeState, ref: str) -> Any:
        current: Any = state
        for part in ref.split("."):
            current = getattr(current, part, None)
            if current is None:
                return None
        return current

    @staticmethod
    def _safe_run_ref(run_dir: Path, ref: str) -> Path:
        path = (run_dir / ref).resolve()
        if run_dir.resolve() not in path.parents and path != run_dir.resolve():
            raise WorkflowRecoverableError(f"产物路径越界: {ref}")
        return path
