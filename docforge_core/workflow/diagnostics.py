"""Read-only workflow health diagnostics for product acceptance."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from docforge_core.domain.enums import NextAction, WorkflowStatus
from docforge_core.domain.schemas import (
    DocForgeState,
    DraftAuditReport,
    DraftQualityGateReport,
    ExportManifest,
)
from docforge_core.io.run_paths import get_run_dir
from docforge_core.io.state_store import StateStore

from .orchestrator import HUMAN_CONFIRMATION_STATES, TERMINAL_STATES
from .user_facing_errors import UserFacingErrorMapper


class WorkflowIssueSeverity(StrEnum):
    """Diagnostic issue severity."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class WorkflowIssue:
    """One workflow health issue."""

    severity: WorkflowIssueSeverity
    code: str
    message: str
    user_message: str
    developer_message: str = ""
    related_artifact_ref: str | None = None
    suggested_action: str = ""


@dataclass(frozen=True, slots=True)
class WorkflowHealthReport:
    """Read-only status report suitable for product and developer tooling."""

    run_id: str
    workflow_status: str
    next_action: str
    is_healthy: bool
    can_continue: bool
    needs_human_confirmation: bool
    is_terminal: bool
    can_download_docx: bool
    exported_docx_path: str | None
    issues: list[WorkflowIssue] = field(default_factory=list)
    user_message: str = ""
    developer_message: str = ""
    suggested_user_action: str = ""
    checked_at: str = ""


class WorkflowDiagnosticsService:
    """Inspect state and artifacts without changing anything."""

    def __init__(
        self,
        state_store: StateStore | None = None,
        error_mapper: UserFacingErrorMapper | None = None,
    ) -> None:
        self.state_store = state_store or StateStore()
        self.error_mapper = error_mapper or UserFacingErrorMapper()

    def inspect(self, run_id: str) -> WorkflowHealthReport:
        state = self.state_store.load_state(run_id)
        issues: list[WorkflowIssue] = []
        run_dir = get_run_dir(run_id, self.state_store.data_dir)

        self._check_status_action(state, issues)
        self._check_state_artifact_refs(state, run_dir, issues)
        self._check_lineage_hashes(state, run_dir, issues)
        self._check_export_manifest(state, run_dir, issues)

        is_terminal = state.workflow_status in TERMINAL_STATES
        needs_confirmation = state.workflow_status in HUMAN_CONFIRMATION_STATES
        exported_path = self._exported_docx_path(state, run_dir)
        can_download = bool(exported_path and exported_path.exists() and is_terminal)
        has_error = any(item.severity == WorkflowIssueSeverity.ERROR for item in issues)
        is_healthy = not has_error
        can_continue = (
            is_healthy
            and not is_terminal
            and not needs_confirmation
            and state.next_action not in {NextAction.STOP, NextAction.INGEST_MATERIALS}
        )
        if not issues:
            issues.append(
                WorkflowIssue(
                    severity=WorkflowIssueSeverity.INFO,
                    code="healthy",
                    message="workflow health check passed",
                    user_message="当前任务状态正常。",
                    developer_message="no diagnostic issues",
                    suggested_action=self._suggested_action(state, can_download),
                )
            )
        user_issue = self._primary_user_issue(issues)
        return WorkflowHealthReport(
            run_id=run_id,
            workflow_status=state.workflow_status.value,
            next_action=state.next_action.value,
            is_healthy=is_healthy,
            can_continue=can_continue,
            needs_human_confirmation=needs_confirmation,
            is_terminal=is_terminal,
            can_download_docx=can_download,
            exported_docx_path=str(exported_path) if can_download and exported_path else None,
            issues=issues,
            user_message=user_issue.user_message,
            developer_message="; ".join(
                item.developer_message or item.message for item in issues
            ),
            suggested_user_action=(
                user_issue.suggested_action or self._suggested_action(state, can_download)
            ),
            checked_at=datetime.now(UTC).isoformat(),
        )

    def _check_status_action(
        self,
        state: DocForgeState,
        issues: list[WorkflowIssue],
    ) -> None:
        if state.workflow_status == WorkflowStatus.CREATED and state.next_action != NextAction.INGEST_MATERIALS:
            issues.append(self._issue("status_action_mismatch", "当前状态与下一步动作不一致。"))
        if state.workflow_status in TERMINAL_STATES and state.next_action != NextAction.STOP:
            issues.append(self._issue("terminal_next_action_mismatch", "终态任务的 next_action 必须为 STOP。"))
        if state.workflow_status == WorkflowStatus.USER_CONFIRM_REQUIRED and state.next_action != NextAction.ASK_HUMAN_CONFIRMATION:
            issues.append(self._issue("confirmation_next_action_mismatch", "人工确认状态的下一步动作不一致。"))

    def _check_state_artifact_refs(
        self,
        state: DocForgeState,
        run_dir: Path,
        issues: list[WorkflowIssue],
    ) -> None:
        refs: list[str] = []
        refs.extend(item.content_ref for item in state.draft_versions if item.content_ref)
        refs.extend(
            ref
            for ref in (
                state.figure_slots_ref,
                state.audit_report_ref,
                state.draft_quality_gate_report_ref,
                state.final_doc_path,
            )
            if ref
        )
        if state.export_result and state.export_result.docx_path:
            refs.append(state.export_result.docx_path)
        for ref in refs:
            path = self._safe_run_ref(run_dir, ref)
            if path is None or not path.exists():
                issues.append(
                    self._issue(
                        "artifact_ref_missing",
                        "当前流程文件不完整，不能继续。请重新开始一个任务或联系开发者检查数据目录。",
                        developer=f"state artifact ref missing: {ref}",
                        ref=ref,
                    )
                )

    def _check_lineage_hashes(
        self,
        state: DocForgeState,
        run_dir: Path,
        issues: list[WorkflowIssue],
    ) -> None:
        if not state.audit_report_ref:
            return
        audit_path = self._safe_run_ref(run_dir, state.audit_report_ref)
        if audit_path is None or not audit_path.exists():
            return
        try:
            audit = DraftAuditReport.model_validate(self._load_json(audit_path))
        except Exception as exc:
            issues.append(self._issue("audit_report_invalid", "审计报告无法读取。", developer=str(exc), ref=state.audit_report_ref))
            return
        self._check_hash(
            issues,
            run_dir,
            audit.source_draft_ref,
            audit.source_draft_hash,
            "audit_report source_draft_hash mismatch",
        )
        self._check_hash(
            issues,
            run_dir,
            audit.source_figure_slots_ref,
            audit.source_figure_slots_hash,
            "audit_report source_figure_slots_hash mismatch",
        )
        if not state.draft_quality_gate_report_ref:
            return
        gate_path = self._safe_run_ref(run_dir, state.draft_quality_gate_report_ref)
        if gate_path is None or not gate_path.exists():
            return
        try:
            gate = DraftQualityGateReport.model_validate(self._load_json(gate_path))
        except Exception as exc:
            issues.append(self._issue("quality_gate_report_invalid", "质量门禁报告无法读取。", developer=str(exc), ref=state.draft_quality_gate_report_ref))
            return
        self._check_hash(
            issues,
            run_dir,
            gate.source_audit_report_path,
            gate.source_audit_report_hash,
            "quality_gate_report source_audit_report_hash mismatch",
        )
        self._check_hash(
            issues,
            run_dir,
            gate.source_draft_ref,
            gate.source_draft_hash,
            "quality_gate_report source_draft_hash mismatch",
        )
        self._check_hash(
            issues,
            run_dir,
            gate.source_figure_slots_ref,
            gate.source_figure_slots_hash,
            "quality_gate_report source_figure_slots_hash mismatch",
        )

    def _check_export_manifest(
        self,
        state: DocForgeState,
        run_dir: Path,
        issues: list[WorkflowIssue],
    ) -> None:
        if state.export_result is None:
            return
        manifest_path = run_dir / "exports" / "export_manifest.json"
        if not manifest_path.exists():
            issues.append(
                self._issue(
                    "export_manifest_missing",
                    "导出记录不完整，不能确认 DOCX 可信度。",
                    developer="export_manifest.json missing",
                    ref="exports/export_manifest.json",
                )
            )
            return
        try:
            manifest = ExportManifest.model_validate(self._load_json(manifest_path))
        except Exception as exc:
            issues.append(self._issue("export_manifest_invalid", "导出记录无法读取。", developer=str(exc), ref="exports/export_manifest.json"))
            return
        self._check_hash(
            issues,
            run_dir,
            manifest.output_docx_path,
            manifest.output_docx_hash,
            "export_manifest output_docx_hash mismatch",
        )
        self._check_hash(
            issues,
            run_dir,
            manifest.source_quality_gate_report_ref,
            manifest.source_quality_gate_report_hash,
            "export_manifest source_quality_gate_report_hash mismatch",
        )

    def _check_hash(
        self,
        issues: list[WorkflowIssue],
        run_dir: Path,
        ref: str,
        expected_hash: str,
        developer: str,
    ) -> None:
        path = self._safe_run_ref(run_dir, ref)
        if path is None or not path.exists():
            issues.append(
                self._issue(
                    "artifact_ref_missing",
                    "当前流程文件不完整，不能继续。请重新开始一个任务或联系开发者检查数据目录。",
                    developer=f"state artifact ref missing: {ref}",
                    ref=ref,
                )
            )
            return
        if self._sha256(path) != expected_hash:
            issues.append(
                self._issue(
                    "artifact_hash_mismatch",
                    "流程产物已被修改，系统已停止继续执行以保护文档可信度。",
                    developer=developer,
                    ref=ref,
                )
            )

    def _issue(
        self,
        code: str,
        user_message: str,
        *,
        developer: str | None = None,
        ref: str | None = None,
        severity: WorkflowIssueSeverity = WorkflowIssueSeverity.ERROR,
    ) -> WorkflowIssue:
        mapped = self.error_mapper.map_error(developer or code)
        return WorkflowIssue(
            severity=severity,
            code=code,
            message=code,
            user_message=user_message or mapped.user_message,
            developer_message=developer or mapped.developer_message,
            related_artifact_ref=ref,
            suggested_action=mapped.suggested_action,
        )

    @staticmethod
    def _primary_user_issue(issues: list[WorkflowIssue]) -> WorkflowIssue:
        for severity in (
            WorkflowIssueSeverity.ERROR,
            WorkflowIssueSeverity.WARNING,
            WorkflowIssueSeverity.INFO,
        ):
            for issue in issues:
                if issue.severity == severity:
                    return issue
        return issues[0]

    @staticmethod
    def _suggested_action(state: DocForgeState, can_download: bool) -> str:
        if can_download:
            return "下载 DOCX。"
        if state.workflow_status == WorkflowStatus.CREATED:
            return "上传资料或加载本地样例工程。"
        if state.workflow_status == WorkflowStatus.USER_CONFIRM_REQUIRED:
            return "确认模板后继续。"
        if state.workflow_status in TERMINAL_STATES:
            return "当前任务已完成。"
        return "执行下一步或继续到人工确认点。"

    @staticmethod
    def _exported_docx_path(state: DocForgeState, run_dir: Path) -> Path | None:
        if state.export_result is None or not state.export_result.docx_path:
            return None
        return run_dir / state.export_result.docx_path

    @staticmethod
    def _safe_run_ref(run_dir: Path, ref: str) -> Path | None:
        if not isinstance(ref, str) or not ref.strip():
            return None
        candidate = (run_dir / ref).resolve()
        try:
            candidate.relative_to(run_dir.resolve())
        except ValueError:
            return None
        return candidate

    @staticmethod
    def _load_json(path: Path) -> dict[str, Any]:
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError("artifact JSON must be object")
        return value

    @staticmethod
    def _sha256(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()
