import pytest

from docforge_core.domain.enums import NextAction, WorkflowStatus
from docforge_core.gates.draft_quality_gate import DraftQualityGateService

from .test_audit_agent import (
    _audit_path,
    _audit_ready_state,
    _draft_path,
    _first_section,
    _load_json,
    _replace_first_section,
    _run_audit,
    _sha256,
    _write_json,
)
from .test_figure_slot_planner import _figure_path


def _quality_path(store, run_id: str, version: int = 1):
    return store.data_dir / "runs" / run_id / "drafts" / f"quality_gate_report_v{version}.json"


def _draft_path_for_version(store, run_id: str, version: int):
    return store.data_dir / "runs" / run_id / "drafts" / f"draft_v{version}.json"


def _write_v3_audit_fixture(store, state, report, *, damage_summary: bool = False) -> None:
    draft_v3_path = _draft_path_for_version(store, state.run_id, 3)
    draft_v3 = _load_json(_draft_path(store, state.run_id))
    draft_v3["version_label"] = "v3"
    draft_v3["previous_version"] = "v2"
    _write_json(draft_v3_path, draft_v3)
    payload = report.model_dump(mode="json")
    payload["report_id"] = f"audit_v3_{state.run_id}"
    payload["draft_version"] = "v3"
    payload["source_draft_ref"] = "drafts/draft_v3.json"
    payload["source_draft_hash"] = _sha256(draft_v3_path)
    payload["source_figure_slots_ref"] = "drafts/figure_slots_v1.json"
    payload["source_figure_slots_hash"] = _sha256(_figure_path(store, state.run_id))
    if damage_summary:
        payload["summary"]["blocker_count"] = 0
    audit_v3 = _audit_path(store, state.run_id).with_name("audit_report_v3.json")
    _write_json(audit_v3, payload)
    reloaded = store.load_state(state.run_id)
    reloaded.workflow_status = WorkflowStatus.DRAFT_V3_AUDITED
    reloaded.next_action = NextAction.RUN_DRAFT_QUALITY_GATE
    reloaded.current_draft_version = "v3"
    reloaded.audit_report_ref = "drafts/audit_report_v3.json"
    reloaded.audit_report_result_id = payload["report_id"]
    store.save_state(reloaded)


def test_draft_quality_gate_passes_minor_or_suggestion_only_audit(tmp_path) -> None:
    store, state, provider = _audit_ready_state(tmp_path)
    report = _run_audit(store, state, provider)
    assert report.summary.blocker_count == 0
    assert report.summary.major_count == 0

    result = DraftQualityGateService(store).run(state.run_id)

    reloaded = store.load_state(state.run_id)
    assert result.passed is True
    assert result.next_workflow_status == WorkflowStatus.DRAFT_QUALITY_GATE_PASSED
    assert result.next_action == NextAction.EXPORT_DOCX
    assert _quality_path(store, state.run_id).exists()
    assert reloaded.workflow_status == WorkflowStatus.DRAFT_QUALITY_GATE_PASSED
    assert reloaded.next_action == NextAction.EXPORT_DOCX


def test_draft_quality_gate_requires_revision_for_blocker_or_major_before_v3(tmp_path) -> None:
    store, state, provider = _audit_ready_state(tmp_path)
    section = _first_section(store, state.run_id)
    section["citations"] = [{"evidence_id": "ev_missing", "quote": "missing quote"}]
    _replace_first_section(store, state.run_id, section)
    report = _run_audit(store, state, provider)
    assert report.summary.blocker_count > 0

    result = DraftQualityGateService(store).run(state.run_id)

    reloaded = store.load_state(state.run_id)
    assert result.passed is False
    assert result.decision.value == "require_revision"
    assert result.blocking_finding_ids
    assert reloaded.workflow_status == WorkflowStatus.DRAFT_REVISION_REQUIRED
    assert reloaded.next_action == NextAction.REVISE_DRAFT


def test_draft_quality_gate_rejects_draft_changed_after_audit(tmp_path) -> None:
    store, state, provider = _audit_ready_state(tmp_path)
    _run_audit(store, state, provider)
    draft = _load_json(_draft_path(store, state.run_id))
    draft["chapters"][0]["sections"][0]["content"] += "\n审计后篡改内容。"
    _write_json(_draft_path(store, state.run_id), draft)

    with pytest.raises(ValueError, match="source_draft_hash|不匹配"):
        DraftQualityGateService(store).run(state.run_id)

    reloaded = store.load_state(state.run_id)
    assert reloaded.workflow_status == WorkflowStatus.DRAFT_AUDITED
    assert reloaded.next_action == NextAction.RUN_DRAFT_QUALITY_GATE
    assert not _quality_path(store, state.run_id).exists()


def test_draft_quality_gate_rejects_figure_slots_changed_after_audit(tmp_path) -> None:
    store, state, provider = _audit_ready_state(tmp_path)
    _run_audit(store, state, provider)
    figures = _load_json(_figure_path(store, state.run_id))
    figures["figure_slots"][0]["recommended_caption"] = "审计后篡改图注"
    _write_json(_figure_path(store, state.run_id), figures)

    with pytest.raises(ValueError, match="source_figure_slots_hash|不匹配"):
        DraftQualityGateService(store).run(state.run_id)

    reloaded = store.load_state(state.run_id)
    assert reloaded.workflow_status == WorkflowStatus.DRAFT_AUDITED
    assert reloaded.next_action == NextAction.RUN_DRAFT_QUALITY_GATE
    assert not _quality_path(store, state.run_id).exists()


def test_draft_quality_gate_rejects_state_audit_report_ref_mismatch(tmp_path) -> None:
    store, state, provider = _audit_ready_state(tmp_path)
    _run_audit(store, state, provider)
    reloaded = store.load_state(state.run_id)
    reloaded.audit_report_ref = "drafts/audit_report_v2.json"
    store.save_state(reloaded)

    with pytest.raises(ValueError, match="state.audit_report_ref|不匹配"):
        DraftQualityGateService(store).run(state.run_id, draft_version=1)

    final = store.load_state(state.run_id)
    assert final.workflow_status == WorkflowStatus.DRAFT_AUDITED
    assert final.next_action == NextAction.RUN_DRAFT_QUALITY_GATE
    assert not _quality_path(store, state.run_id).exists()


def test_draft_quality_gate_rejects_state_audit_report_result_id_mismatch(tmp_path) -> None:
    store, state, provider = _audit_ready_state(tmp_path)
    _run_audit(store, state, provider)
    reloaded = store.load_state(state.run_id)
    reloaded.audit_report_result_id = "audit_result_wrong"
    store.save_state(reloaded)

    with pytest.raises(ValueError, match="state.audit_report_result_id|不匹配"):
        DraftQualityGateService(store).run(state.run_id)

    final = store.load_state(state.run_id)
    assert final.workflow_status == WorkflowStatus.DRAFT_AUDITED
    assert final.next_action == NextAction.RUN_DRAFT_QUALITY_GATE
    assert not _quality_path(store, state.run_id).exists()


def test_quality_gate_report_records_source_draft_and_figure_hash(tmp_path) -> None:
    store, state, provider = _audit_ready_state(tmp_path)
    _run_audit(store, state, provider)

    result = DraftQualityGateService(store).run(state.run_id)

    audit = _load_json(_audit_path(store, state.run_id))
    saved = _load_json(_quality_path(store, state.run_id))
    assert result.source_draft_ref == audit["source_draft_ref"]
    assert result.source_draft_hash == audit["source_draft_hash"]
    assert result.source_figure_slots_ref == audit["source_figure_slots_ref"]
    assert result.source_figure_slots_hash == audit["source_figure_slots_hash"]
    assert saved["source_draft_ref"] == audit["source_draft_ref"]
    assert saved["source_draft_hash"] == _sha256(_draft_path(store, state.run_id))
    assert saved["source_figure_slots_ref"] == audit["source_figure_slots_ref"]
    assert saved["source_figure_slots_hash"] == _sha256(_figure_path(store, state.run_id))


def test_draft_quality_gate_rejects_missing_audit_report_without_state_advance(tmp_path) -> None:
    store, state, _provider = _audit_ready_state(tmp_path)
    state.workflow_status = WorkflowStatus.DRAFT_AUDITED
    state.next_action = NextAction.RUN_DRAFT_QUALITY_GATE
    store.save_state(state)

    with pytest.raises(ValueError, match="缺失"):
        DraftQualityGateService(store).run(state.run_id)

    reloaded = store.load_state(state.run_id)
    assert reloaded.workflow_status == WorkflowStatus.DRAFT_AUDITED
    assert reloaded.next_action == NextAction.RUN_DRAFT_QUALITY_GATE
    assert not _quality_path(store, state.run_id).exists()


def test_draft_quality_gate_sends_failed_v3_to_risk_path(tmp_path) -> None:
    store, state, provider = _audit_ready_state(tmp_path)
    section = _first_section(store, state.run_id)
    section["citations"] = [{"evidence_id": "ev_missing", "quote": "missing quote"}]
    _replace_first_section(store, state.run_id, section)
    report = _run_audit(store, state, provider)
    _write_v3_audit_fixture(store, state, report)

    result = DraftQualityGateService(store).run(state.run_id, draft_version=3)

    assert result.passed is False
    assert result.decision.value == "risk_export_required"
    final = store.load_state(state.run_id)
    assert final.workflow_status == WorkflowStatus.RISK_VERSION_READY
    assert final.next_action == NextAction.EXPORT_RISK_DOCX


def test_draft_quality_gate_schema_summary_mismatch_fails_closed(tmp_path) -> None:
    store, state, provider = _audit_ready_state(tmp_path)
    _run_audit(store, state, provider)
    payload = _load_json(_audit_path(store, state.run_id))
    payload["summary"]["blocker_count"] = 99
    _write_json(_audit_path(store, state.run_id), payload)

    with pytest.raises(ValueError, match="fail closed"):
        DraftQualityGateService(store).run(state.run_id)

    reloaded = store.load_state(state.run_id)
    assert reloaded.workflow_status == WorkflowStatus.DRAFT_AUDITED
    assert reloaded.next_action == NextAction.RUN_DRAFT_QUALITY_GATE
    assert not _quality_path(store, state.run_id).exists()


def test_draft_quality_gate_total_findings_mismatch_fails_closed(tmp_path) -> None:
    store, state, provider = _audit_ready_state(tmp_path)
    _run_audit(store, state, provider)
    payload = _load_json(_audit_path(store, state.run_id))
    payload["summary"]["total_findings"] = 999
    _write_json(_audit_path(store, state.run_id), payload)

    with pytest.raises(ValueError, match="fail closed"):
        DraftQualityGateService(store).run(state.run_id)

    reloaded = store.load_state(state.run_id)
    assert reloaded.workflow_status == WorkflowStatus.DRAFT_AUDITED
    assert reloaded.next_action == NextAction.RUN_DRAFT_QUALITY_GATE
    assert not _quality_path(store, state.run_id).exists()


def test_draft_quality_gate_overall_false_without_blocker_fails_closed(tmp_path) -> None:
    store, state, provider = _audit_ready_state(tmp_path)
    _run_audit(store, state, provider)
    payload = _load_json(_audit_path(store, state.run_id))
    payload["overall_passed"] = False
    _write_json(_audit_path(store, state.run_id), payload)

    with pytest.raises(ValueError, match="fail closed"):
        DraftQualityGateService(store).run(state.run_id)

    reloaded = store.load_state(state.run_id)
    assert reloaded.workflow_status == WorkflowStatus.DRAFT_AUDITED
    assert reloaded.next_action == NextAction.RUN_DRAFT_QUALITY_GATE
    assert not _quality_path(store, state.run_id).exists()


def test_draft_quality_gate_damaged_v3_audit_does_not_enter_risk_path(tmp_path) -> None:
    store, state, provider = _audit_ready_state(tmp_path)
    section = _first_section(store, state.run_id)
    section["citations"] = [{"evidence_id": "ev_missing", "quote": "missing quote"}]
    _replace_first_section(store, state.run_id, section)
    report = _run_audit(store, state, provider)
    _write_v3_audit_fixture(store, state, report, damage_summary=True)

    with pytest.raises(ValueError, match="fail closed"):
        DraftQualityGateService(store).run(state.run_id, draft_version=3)

    final = store.load_state(state.run_id)
    assert final.workflow_status == WorkflowStatus.DRAFT_V3_AUDITED
    assert final.next_action == NextAction.RUN_DRAFT_QUALITY_GATE
    assert not _quality_path(store, state.run_id, version=3).exists()
