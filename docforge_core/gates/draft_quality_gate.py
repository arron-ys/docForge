"""Sprint 12 draft quality gate driven only by DraftAuditReport."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from docforge_core.domain.enums import (
    AuditSeverity,
    DraftQualityGateDecision,
    GateType,
    NextAction,
    WorkflowStatus,
)
from docforge_core.domain.schemas import (
    DocForgeState,
    DraftAuditReport,
    DraftQualityGateFindingSummary,
    DraftQualityGateReport,
    QualityGateReport,
)
from docforge_core.io.run_paths import get_drafts_dir, get_state_file
from docforge_core.io.state_store import StateStore


class DraftQualityGateService:
    """Convert audit_report_vN.json into quality_gate_report_vN.json and state."""

    def __init__(self, state_store: StateStore | None = None) -> None:
        self.state_store = state_store or StateStore()

    def run(self, run_id: str, draft_version: int | None = None) -> DraftQualityGateReport:
        state = self.state_store.load_state(run_id)
        version = draft_version or self._current_draft_number(state)
        self._require_ready_state(state, version)
        paths = self._paths(run_id, version)
        report = self._load_audit_report(paths["audit"], version)
        self._validate_audit_report_bound_to_artifacts(report, state, paths, version)
        self._validate_audit_report_consistency(report)
        gate_report = self.build_report(report, paths["audit"], version)
        state_path = get_state_file(run_id, self.state_store.data_dir)
        original_state = state_path.read_bytes()
        tmp_path = paths["quality"].with_suffix(paths["quality"].suffix + ".tmp")
        if tmp_path.exists():
            tmp_path.unlink()
        if paths["quality"].exists():
            raise ValueError(f"quality_gate_report_v{version}.json 已存在，不允许覆盖")

        try:
            tmp_path.write_text(
                json.dumps(gate_report.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            tmp_path.replace(paths["quality"])
            self._apply_success_state(state, gate_report)
            self.state_store.save_state(state)
            self._validate_success_state(
                self.state_store.load_state(run_id),
                gate_report,
                version,
                paths["quality"],
            )
        except Exception:
            if tmp_path.exists():
                tmp_path.unlink()
            if paths["quality"].exists():
                paths["quality"].unlink()
            self._restore_state_file(state_path, original_state)
            raise
        return gate_report

    def build_report(
        self,
        audit_report: DraftAuditReport,
        audit_path: Path,
        draft_version: int,
    ) -> DraftQualityGateReport:
        counts = DraftQualityGateFindingSummary(
            blocker=sum(item.severity == AuditSeverity.BLOCKER for item in audit_report.findings),
            major=sum(item.severity == AuditSeverity.MAJOR for item in audit_report.findings),
            minor=sum(item.severity == AuditSeverity.MINOR for item in audit_report.findings),
            suggestion=sum(item.severity == AuditSeverity.SUGGESTION for item in audit_report.findings),
        )
        blocking_ids = [
            item.finding_id
            for item in audit_report.findings
            if item.severity == AuditSeverity.BLOCKER
        ]
        major_ids = [
            item.finding_id
            for item in audit_report.findings
            if item.severity == AuditSeverity.MAJOR
        ]
        minor_ids = [
            item.finding_id
            for item in audit_report.findings
            if item.severity == AuditSeverity.MINOR
        ]
        suggestion_ids = [
            item.finding_id
            for item in audit_report.findings
            if item.severity == AuditSeverity.SUGGESTION
        ]
        hard_failed = bool(blocking_ids or major_ids)
        if hard_failed and draft_version == 3:
            passed = False
            decision = DraftQualityGateDecision.RISK_EXPORT_REQUIRED
            next_status = WorkflowStatus.RISK_VERSION_READY
            next_action = NextAction.EXPORT_RISK_DOCX
        elif hard_failed:
            passed = False
            decision = DraftQualityGateDecision.REQUIRE_REVISION
            next_status = WorkflowStatus.DRAFT_REVISION_REQUIRED
            next_action = NextAction.REVISE_DRAFT
        else:
            passed = True
            decision = DraftQualityGateDecision.EXPORT_DOCX
            next_status = WorkflowStatus.DRAFT_QUALITY_GATE_PASSED
            next_action = NextAction.EXPORT_DOCX

        return DraftQualityGateReport(
            draft_version=f"v{draft_version}",  # type: ignore[arg-type]
            source_audit_report_path=f"drafts/audit_report_v{draft_version}.json",
            source_audit_report_hash=self.sha256(audit_path),
            source_draft_ref=audit_report.source_draft_ref,
            source_draft_hash=audit_report.source_draft_hash,
            source_figure_slots_ref=audit_report.source_figure_slots_ref,
            source_figure_slots_hash=audit_report.source_figure_slots_hash,
            audit_overall_passed=audit_report.overall_passed,
            passed=passed,
            decision=decision,
            severity_counts=counts,
            blocking_finding_ids=blocking_ids,
            major_finding_ids=major_ids,
            minor_finding_ids=minor_ids,
            suggestion_finding_ids=suggestion_ids,
            warnings=[],
            fail_closed_reason=None,
            next_workflow_status=next_status,
            next_action=next_action,
        )

    def _load_audit_report(self, path: Path, draft_version: int) -> DraftAuditReport:
        if not path.exists():
            raise ValueError(f"audit_report_v{draft_version}.json 缺失")
        try:
            raw: Any = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise ValueError(f"audit_report_v{draft_version}.json 无法解析") from exc
        try:
            report = DraftAuditReport.model_validate(raw)
        except ValidationError as exc:
            raise ValueError(f"audit_report_v{draft_version}.json schema 不合法") from exc
        if report.draft_version != f"v{draft_version}":
            raise ValueError("audit_report draft_version 与当前 draft_version 不一致")
        if report.source_draft_ref != f"drafts/draft_v{draft_version}.json":
            raise ValueError("audit_report source_draft_ref 与当前 draft_version 不一致")
        if report.source_figure_slots_ref != "drafts/figure_slots_v1.json":
            raise ValueError("audit_report source_figure_slots_ref 与当前图位文件不一致")
        return report

    def _validate_audit_report_bound_to_artifacts(
        self,
        report: DraftAuditReport,
        state: DocForgeState,
        paths: dict[str, Path],
        draft_version: int,
    ) -> None:
        expected_audit_ref = f"drafts/audit_report_v{draft_version}.json"
        expected_draft_ref = f"drafts/draft_v{draft_version}.json"
        expected_figure_ref = "drafts/figure_slots_v1.json"
        if state.audit_report_ref != expected_audit_ref:
            raise ValueError("state.audit_report_ref 不匹配，DraftQualityGate fail closed")
        if state.audit_report_result_id != report.report_id:
            raise ValueError("state.audit_report_result_id 不匹配，DraftQualityGate fail closed")
        if report.source_draft_ref != expected_draft_ref:
            raise ValueError("source_draft_ref 不匹配，DraftQualityGate fail closed")
        if report.source_figure_slots_ref != expected_figure_ref:
            raise ValueError("source_figure_slots_ref 不匹配，DraftQualityGate fail closed")
        if not paths["draft"].exists():
            raise ValueError("source_draft_hash 不匹配，draft 文件缺失")
        if not paths["figure"].exists():
            raise ValueError("source_figure_slots_hash 不匹配，figure_slots 文件缺失")
        if report.source_draft_hash != self.sha256(paths["draft"]):
            raise ValueError("source_draft_hash 不匹配，DraftQualityGate fail closed")
        if report.source_figure_slots_hash != self.sha256(paths["figure"]):
            raise ValueError("source_figure_slots_hash 不匹配，DraftQualityGate fail closed")

    @staticmethod
    def _validate_audit_report_consistency(report: DraftAuditReport) -> None:
        counts = {
            AuditSeverity.BLOCKER: sum(
                item.severity == AuditSeverity.BLOCKER for item in report.findings
            ),
            AuditSeverity.MAJOR: sum(
                item.severity == AuditSeverity.MAJOR for item in report.findings
            ),
            AuditSeverity.MINOR: sum(
                item.severity == AuditSeverity.MINOR for item in report.findings
            ),
            AuditSeverity.SUGGESTION: sum(
                item.severity == AuditSeverity.SUGGESTION for item in report.findings
            ),
        }
        summary = report.summary
        summary_mismatch = (
            summary.blocker_count != counts[AuditSeverity.BLOCKER]
            or summary.major_count != counts[AuditSeverity.MAJOR]
            or summary.minor_count != counts[AuditSeverity.MINOR]
            or summary.suggestion_count != counts[AuditSeverity.SUGGESTION]
            or summary.total_findings != len(report.findings)
        )
        if summary_mismatch:
            raise ValueError(
                "audit_report summary 与 findings 不一致，DraftQualityGate fail closed"
            )
        expected_overall_passed = counts[AuditSeverity.BLOCKER] == 0
        if report.overall_passed != expected_overall_passed:
            raise ValueError(
                "audit_report overall_passed 与 findings 不一致，DraftQualityGate fail closed"
            )

    @staticmethod
    def _current_draft_number(state: DocForgeState) -> int:
        if state.current_draft_version in {"v1", "v2", "v3"}:
            return int(state.current_draft_version[1])
        if state.audit_report_ref:
            stem = Path(state.audit_report_ref).stem
            if stem in {"audit_report_v1", "audit_report_v2", "audit_report_v3"}:
                return int(stem[-1])
        raise ValueError("无法确定当前 draft_version")

    @staticmethod
    def _require_ready_state(state: DocForgeState, version: int) -> None:
        allowed_status = {
            1: {WorkflowStatus.DRAFT_AUDITED},
            2: {WorkflowStatus.DRAFT_V2_AUDITED, WorkflowStatus.AUDIT_V2_COMPLETED},
            3: {WorkflowStatus.DRAFT_V3_AUDITED, WorkflowStatus.AUDIT_V3_COMPLETED},
        }[version]
        if state.workflow_status not in allowed_status:
            raise ValueError("DraftQualityGate 要求当前草稿已完成 AuditAgent 审计")
        if state.next_action != NextAction.RUN_DRAFT_QUALITY_GATE:
            raise ValueError("DraftQualityGate 要求 next_action 为 RUN_DRAFT_QUALITY_GATE")

    def _paths(self, run_id: str, version: int) -> dict[str, Path]:
        drafts_dir = get_drafts_dir(run_id, self.state_store.data_dir)
        return {
            "audit": drafts_dir / f"audit_report_v{version}.json",
            "quality": drafts_dir / f"quality_gate_report_v{version}.json",
            "draft": drafts_dir / f"draft_v{version}.json",
            "figure": drafts_dir / "figure_slots_v1.json",
        }

    @staticmethod
    def _apply_success_state(
        state: DocForgeState,
        gate_report: DraftQualityGateReport,
    ) -> None:
        state.workflow_status = gate_report.next_workflow_status
        state.next_action = gate_report.next_action
        state.draft_quality_gate_report_ref = (
            f"drafts/quality_gate_report_{gate_report.draft_version}.json"
        )
        state.draft_quality_gate_reports.append(
            QualityGateReport(
                gate_type=GateType.DRAFT_QUALITY_GATE,
                target_id=gate_report.draft_version,
                passed=gate_report.passed,
                blocker_issues=list(gate_report.blocking_finding_ids),
                major_issues=list(gate_report.major_finding_ids),
                minor_issues=list(gate_report.minor_finding_ids),
                summary=gate_report.fail_closed_reason or gate_report.decision.value,
                next_action=gate_report.next_action,
            )
        )
        state.blocker_issues = list(gate_report.blocking_finding_ids)
        state.major_issues = list(gate_report.major_finding_ids)
        state.minor_issues = list(gate_report.minor_finding_ids)

    @staticmethod
    def _validate_success_state(
        state: DocForgeState,
        gate_report: DraftQualityGateReport,
        version: int,
        report_path: Path,
    ) -> None:
        if not report_path.exists():
            raise ValueError("DraftQualityGate 成功状态缺少 quality_gate_report")
        if state.workflow_status != gate_report.next_workflow_status:
            raise ValueError("DraftQualityGate 成功状态 workflow_status 不正确")
        if state.next_action != gate_report.next_action:
            raise ValueError("DraftQualityGate 成功状态 next_action 不正确")
        if state.draft_quality_gate_report_ref != f"drafts/quality_gate_report_v{version}.json":
            raise ValueError("DraftQualityGate 成功状态 report_ref 不正确")

    @staticmethod
    def sha256(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    @staticmethod
    def _restore_state_file(state_path: Path, original: bytes) -> None:
        rollback = state_path.with_suffix(".json.draft_gate_rollback.tmp")
        try:
            rollback.write_bytes(original)
            rollback.replace(state_path)
        finally:
            if rollback.exists():
                rollback.unlink()
