import json

import pytest

from docforge_core.agents.audit_agent import AuditAgentService
from docforge_core.agents.revision_loop_service import RevisionLoopService
from docforge_core.domain.enums import AuditCategory, NextAction, WorkflowStatus
from docforge_core.gates.draft_quality_gate import DraftQualityGateService
from docforge_core.io.state_store import StateStore
from docforge_core.llm.base import LLMMessage
from docforge_core.llm.mock_provider import MockLLMProvider

from .test_audit_agent import (
    _audit_ready_state,
    _draft_path,
    _first_section,
    _load_json,
    _replace_first_section,
    _sha256,
    _write_json,
)
from .test_figure_slot_planner import _figure_path


class RevisionThenAuditProvider(MockLLMProvider):
    def __init__(self) -> None:
        super().__init__(json_response={})

    def generate_json(
        self,
        messages: list[LLMMessage],
        temperature: float = 0.1,
        max_tokens: int | None = None,
    ) -> dict:
        payload = json.loads(messages[1].content)
        if "current_section_content" in payload:
            fixes = payload["finding_list"]
            evidence = payload["allowed_evidence_bundle"][0]
            return {
                "content": evidence["quote"],
                "evidence_ids_used": [evidence["evidence_id"]],
                "citations": [
                    {
                        "evidence_id": evidence["evidence_id"],
                        "quote": evidence["quote"],
                    }
                ],
                "fixed_finding_ids": [fixes[0]["finding_id"]],
                "unresolved_finding_ids": [],
                "warnings": [],
            }
        return {"findings": []}


class FailingRevisionSaveStateStore(StateStore):
    def save_state(self, state):
        raise RuntimeError("injected save_state failure")


class NoRevisionLLMProvider(MockLLMProvider):
    def generate_json(self, messages, temperature=0.1, max_tokens=None):
        raise AssertionError("software identity global fix must not call LLM")


def _failed_gate_ready_state(tmp_path):
    store, state, provider = _audit_ready_state(tmp_path)
    section = _first_section(store, state.run_id)
    section["citations"] = [{"evidence_id": "ev_missing", "quote": "missing quote"}]
    _replace_first_section(store, state.run_id, section)
    service = RevisionLoopService(store, llm_provider=provider)
    service.audit_revised_draft  # keep linter quiet about imported service shape
    AuditAgentService(store, llm_provider=provider).audit_draft(state.run_id)
    RevisionLoopService(store).run_quality_gate_for_current_draft(state.run_id)
    return store, state


def _quality_path(store, run_id: str, version: int = 1):
    return store.data_dir / "runs" / run_id / "drafts" / f"quality_gate_report_v{version}.json"


def _trace_path(store, run_id: str, version: int = 2):
    return store.data_dir / "runs" / run_id / "drafts" / f"revision_trace_v{version}.json"


def _software_identity_failed_gate_ready_state(tmp_path, software_identity: dict):
    store, state, provider = _audit_ready_state(tmp_path)
    draft = _load_json(_draft_path(store, state.run_id))
    draft["software_identity"] = software_identity
    _write_json(_draft_path(store, state.run_id), draft)
    AuditAgentService(store, llm_provider=provider).audit_draft(state.run_id)
    RevisionLoopService(store).run_quality_gate_for_current_draft(state.run_id)
    return store, state


def _assert_no_v2_side_effects(store, run_id: str) -> None:
    assert not (_draft_path(store, run_id).with_name("draft_v2.json")).exists()
    assert not _trace_path(store, run_id).exists()
    reloaded = store.load_state(run_id)
    assert reloaded.workflow_status == WorkflowStatus.DRAFT_REVISION_REQUIRED
    assert reloaded.next_action == NextAction.REVISE_DRAFT


def test_revision_loop_creates_v2_and_requires_reaudit(tmp_path) -> None:
    store, state = _failed_gate_ready_state(tmp_path)
    service = RevisionLoopService(store, llm_provider=RevisionThenAuditProvider())

    result = service.revise_current_draft(state.run_id)

    reloaded = store.load_state(state.run_id)
    draft_v2_path = _draft_path(store, state.run_id).with_name("draft_v2.json")
    assert draft_v2_path.exists()
    assert _trace_path(store, state.run_id).exists()
    assert result.changed_sections
    assert reloaded.workflow_status == WorkflowStatus.DRAFT_V2_CREATED
    assert reloaded.next_action == NextAction.AUDIT_REVISED_DRAFT
    assert reloaded.current_draft_version == "v2"


def test_revision_loop_audits_revised_v2_before_next_gate(tmp_path) -> None:
    store, state = _failed_gate_ready_state(tmp_path)
    service = RevisionLoopService(store, llm_provider=RevisionThenAuditProvider())
    service.revise_current_draft(state.run_id)

    report = service.audit_revised_draft(state.run_id)

    reloaded = store.load_state(state.run_id)
    assert report.draft_version == "v2"
    assert (_draft_path(store, state.run_id).with_name("audit_report_v2.json")).exists()
    assert reloaded.workflow_status == WorkflowStatus.DRAFT_V2_AUDITED
    assert reloaded.next_action == NextAction.RUN_DRAFT_QUALITY_GATE


def test_revision_loop_rejects_v3_revision_attempt(tmp_path) -> None:
    store, state = _failed_gate_ready_state(tmp_path)
    reloaded = store.load_state(state.run_id)
    reloaded.current_draft_version = "v3"
    reloaded.workflow_status = WorkflowStatus.DRAFT_REVISION_REQUIRED
    reloaded.next_action = NextAction.REVISE_DRAFT
    store.save_state(reloaded)

    service = RevisionLoopService(store, llm_provider=RevisionThenAuditProvider())

    with pytest.raises(ValueError, match="v3 不允许继续修订"):
        service.revise_current_draft(state.run_id)


def test_revision_agent_rejects_forged_evidence_id(tmp_path) -> None:
    class ForgingProvider(RevisionThenAuditProvider):
        def generate_json(self, messages, temperature=0.1, max_tokens=None):
            payload = json.loads(messages[1].content)
            if "current_section_content" in payload:
                return {
                    "content": "伪造证据。",
                    "evidence_ids_used": ["ev_forged"],
                    "citations": [{"evidence_id": "ev_forged", "quote": "伪造"}],
                    "fixed_finding_ids": [],
                    "unresolved_finding_ids": [],
                    "warnings": [],
                }
            return {"findings": []}

    store, state = _failed_gate_ready_state(tmp_path)
    service = RevisionLoopService(store, llm_provider=ForgingProvider())

    with pytest.raises(ValueError, match="伪造 evidence_id"):
        service.revise_current_draft(state.run_id)

    assert not (_draft_path(store, state.run_id).with_name("draft_v2.json")).exists()
    assert not _trace_path(store, state.run_id).exists()
    assert store.load_state(state.run_id).workflow_status == WorkflowStatus.DRAFT_REVISION_REQUIRED


def test_revision_agent_repairs_global_software_name_without_llm(tmp_path) -> None:
    store, state = _software_identity_failed_gate_ready_state(
        tmp_path,
        {"target_product_name": "完全错误的软件名称", "version": "V1.0"},
    )

    RevisionLoopService(store, llm_provider=NoRevisionLLMProvider()).revise_current_draft(
        state.run_id
    )

    draft_v2 = _load_json(_draft_path(store, state.run_id).with_name("draft_v2.json"))
    trace = _load_json(_trace_path(store, state.run_id))
    reloaded = store.load_state(state.run_id)
    assert draft_v2["software_identity"] == {
        "target_product_name": "墨衡测试软件",
        "version": "V1.0",
    }
    assert trace["global_fixes_applied"][0]["category"] == (
        AuditCategory.SOFTWARE_IDENTITY_MISMATCH.value
    )
    assert trace["changed_sections"] == []
    assert reloaded.workflow_status == WorkflowStatus.DRAFT_V2_CREATED
    assert reloaded.next_action == NextAction.AUDIT_REVISED_DRAFT


def test_revision_agent_repairs_global_software_version_without_llm(tmp_path) -> None:
    store, state = _software_identity_failed_gate_ready_state(
        tmp_path,
        {"target_product_name": "墨衡测试软件", "version": "V9.9"},
    )

    RevisionLoopService(store, llm_provider=NoRevisionLLMProvider()).revise_current_draft(
        state.run_id
    )

    draft_v2 = _load_json(_draft_path(store, state.run_id).with_name("draft_v2.json"))
    trace = _load_json(_trace_path(store, state.run_id))
    assert draft_v2["software_identity"]["version"] == "V1.0"
    assert trace["global_fixes_applied"][0]["category"] == (
        AuditCategory.SOFTWARE_VERSION_MISMATCH.value
    )


def test_revision_agent_handles_global_and_section_scoped_fixes(tmp_path) -> None:
    store, state, provider = _audit_ready_state(tmp_path)
    draft = _load_json(_draft_path(store, state.run_id))
    draft["software_identity"] = {
        "target_product_name": "完全错误的软件名称",
        "version": "V1.0",
    }
    draft["chapters"][0]["sections"][0]["citations"] = [
        {"evidence_id": "ev_missing", "quote": "missing quote"}
    ]
    _write_json(_draft_path(store, state.run_id), draft)
    AuditAgentService(store, llm_provider=provider).audit_draft(state.run_id)
    RevisionLoopService(store).run_quality_gate_for_current_draft(state.run_id)

    result = RevisionLoopService(
        store,
        llm_provider=RevisionThenAuditProvider(),
    ).revise_current_draft(state.run_id)

    trace = _load_json(_trace_path(store, state.run_id))
    draft_v2 = _load_json(_draft_path(store, state.run_id).with_name("draft_v2.json"))
    assert result.changed_sections
    assert draft_v2["software_identity"]["target_product_name"] == "墨衡测试软件"
    assert trace["global_fixes_applied"]
    assert trace["changed_sections"]
    section_plan_ids = {
        evidence_id
        for plan in store.load_state(state.run_id).section_plan
        for evidence_id in plan.required_evidence_ids
    }
    assert set(trace["evidence_ids_used"]).issubset(section_plan_ids)


def test_revision_agent_rejects_unscoped_non_global_blocker(tmp_path) -> None:
    store, state, provider = _audit_ready_state(tmp_path)
    AuditAgentService(store, llm_provider=provider).audit_draft(state.run_id)
    report = _load_json(_draft_path(store, state.run_id).with_name("audit_report_v1.json"))
    report["overall_passed"] = False
    report["findings"] = [
        {
            "finding_id": "audit_finding_global_bad",
            "severity": "blocker",
            "category": "style_deviation",
            "section_id": None,
            "section_path": [],
            "message": "无法定位的非软件身份全局问题。",
            "claim_text": None,
            "evidence_id": None,
            "quote": None,
            "recommendation": "不得猜测修订。",
            "detector": "deterministic",
            "metadata": {},
        }
    ]
    report["summary"].update(
        {
            "total_findings": 1,
            "blocker_count": 1,
            "major_count": 0,
            "minor_count": 0,
            "suggestion_count": 0,
        }
    )
    _write_json(_draft_path(store, state.run_id).with_name("audit_report_v1.json"), report)
    RevisionLoopService(store).run_quality_gate_for_current_draft(state.run_id)

    with pytest.raises(ValueError, match="无法定位到合法章节"):
        RevisionLoopService(store, llm_provider=RevisionThenAuditProvider()).revise_current_draft(
            state.run_id
        )

    assert not (_draft_path(store, state.run_id).with_name("draft_v2.json")).exists()
    assert not _trace_path(store, state.run_id).exists()
    assert store.load_state(state.run_id).workflow_status == WorkflowStatus.DRAFT_REVISION_REQUIRED


def test_revision_agent_rejects_failed_gate_without_required_fixes(tmp_path) -> None:
    store, state = _failed_gate_ready_state(tmp_path)
    gate = _load_json(_quality_path(store, state.run_id))
    gate["passed"] = False
    gate["blocking_finding_ids"] = []
    gate["major_finding_ids"] = []
    _write_json(_quality_path(store, state.run_id), gate)

    with pytest.raises(ValueError, match="finding_ids|没有可执行 required_fixes|不匹配"):
        RevisionLoopService(store, llm_provider=RevisionThenAuditProvider()).revise_current_draft(
            state.run_id
        )

    assert not (_draft_path(store, state.run_id).with_name("draft_v2.json")).exists()
    assert not _trace_path(store, state.run_id).exists()
    assert store.load_state(state.run_id).workflow_status == WorkflowStatus.DRAFT_REVISION_REQUIRED


def test_revision_agent_cleans_draft_and_trace_when_state_save_fails(tmp_path) -> None:
    store, state = _failed_gate_ready_state(tmp_path)
    failing_store = FailingRevisionSaveStateStore(data_dir=store.data_dir)

    with pytest.raises(RuntimeError, match="save_state failure"):
        RevisionLoopService(
            failing_store,
            llm_provider=RevisionThenAuditProvider(),
        ).revise_current_draft(state.run_id)

    assert not (_draft_path(store, state.run_id).with_name("draft_v2.json")).exists()
    assert not _trace_path(store, state.run_id).exists()
    assert store.load_state(state.run_id).workflow_status == WorkflowStatus.DRAFT_REVISION_REQUIRED


def test_revision_agent_rejects_draft_changed_after_gate(tmp_path) -> None:
    store, state = _failed_gate_ready_state(tmp_path)
    draft = _load_json(_draft_path(store, state.run_id))
    draft["chapters"][0]["sections"][0]["content"] += "\n质量门后篡改内容。"
    _write_json(_draft_path(store, state.run_id), draft)

    with pytest.raises(ValueError, match="source_draft_hash|不匹配"):
        RevisionLoopService(store, llm_provider=RevisionThenAuditProvider()).revise_current_draft(
            state.run_id
        )

    _assert_no_v2_side_effects(store, state.run_id)


def test_revision_agent_rejects_figure_slots_changed_after_gate(tmp_path) -> None:
    store, state = _failed_gate_ready_state(tmp_path)
    figures = _load_json(_figure_path(store, state.run_id))
    figures["figure_slots"][0]["recommended_caption"] = "质量门后篡改图位"
    _write_json(_figure_path(store, state.run_id), figures)

    with pytest.raises(ValueError, match="source_figure_slots_hash|不匹配"):
        RevisionLoopService(store, llm_provider=RevisionThenAuditProvider()).revise_current_draft(
            state.run_id
        )

    _assert_no_v2_side_effects(store, state.run_id)


def test_revision_trace_records_full_artifact_lineage(tmp_path) -> None:
    store, state = _failed_gate_ready_state(tmp_path)

    RevisionLoopService(store, llm_provider=RevisionThenAuditProvider()).revise_current_draft(
        state.run_id
    )

    draft_path = _draft_path(store, state.run_id)
    figure_path = _figure_path(store, state.run_id)
    audit_path = draft_path.with_name("audit_report_v1.json")
    gate_path = _quality_path(store, state.run_id)
    trace = _load_json(_trace_path(store, state.run_id))
    assert trace["source_draft_ref"] == "drafts/draft_v1.json"
    assert trace["source_draft_hash"] == _sha256(draft_path)
    assert trace["source_figure_slots_ref"] == "drafts/figure_slots_v1.json"
    assert trace["source_figure_slots_hash"] == _sha256(figure_path)
    assert trace["source_audit_report_ref"] == "drafts/audit_report_v1.json"
    assert trace["source_audit_report_hash"] == _sha256(audit_path)
    assert trace["source_quality_gate_report_ref"] == "drafts/quality_gate_report_v1.json"
    assert trace["source_quality_gate_report_hash"] == _sha256(gate_path)


def test_revision_agent_writes_revision_trace_v3(tmp_path) -> None:
    store, state = _failed_gate_ready_state(tmp_path)
    service = RevisionLoopService(store, llm_provider=RevisionThenAuditProvider())
    service.revise_current_draft(state.run_id)

    draft_v2_path = _draft_path(store, state.run_id).with_name("draft_v2.json")
    draft_v2 = _load_json(draft_v2_path)
    draft_v2["chapters"][0]["sections"][0]["citations"] = [
        {"evidence_id": "ev_missing", "quote": "missing quote"}
    ]
    _write_json(draft_v2_path, draft_v2)
    service.audit_revised_draft(state.run_id)
    DraftQualityGateService(store).run(state.run_id, draft_version=2)
    reloaded = store.load_state(state.run_id)
    assert reloaded.workflow_status == WorkflowStatus.DRAFT_REVISION_REQUIRED
    assert reloaded.next_action == NextAction.REVISE_DRAFT
    assert reloaded.current_draft_version == "v2"

    service.revise_current_draft(state.run_id)

    trace = _load_json(_trace_path(store, state.run_id, version=3))
    assert trace["from_version"] == "v2"
    assert trace["to_version"] == "v3"
    assert trace["source_audit_report_ref"] == "drafts/audit_report_v2.json"
    assert trace["source_quality_gate_report_ref"] == "drafts/quality_gate_report_v2.json"
    assert (_draft_path(store, state.run_id).with_name("draft_v3.json")).exists()


def test_revision_agent_rejects_stale_gate_report_hash(tmp_path) -> None:
    store, state = _failed_gate_ready_state(tmp_path)
    audit_path = _draft_path(store, state.run_id).with_name("audit_report_v1.json")
    audit = _load_json(audit_path)
    audit["findings"][0]["message"] = "篡改但保持 schema 合法"
    _write_json(audit_path, audit)

    with pytest.raises(ValueError, match="hash|不匹配"):
        RevisionLoopService(store, llm_provider=RevisionThenAuditProvider()).revise_current_draft(
            state.run_id
        )

    _assert_no_v2_side_effects(store, state.run_id)


def test_revision_agent_rejects_gate_report_wrong_source_path(tmp_path) -> None:
    store, state = _failed_gate_ready_state(tmp_path)
    gate_path = _quality_path(store, state.run_id)
    gate = _load_json(gate_path)
    gate["source_audit_report_path"] = "drafts/audit_report_v2.json"
    _write_json(gate_path, gate)

    with pytest.raises(ValueError, match="source_audit_report_path|不匹配"):
        RevisionLoopService(store, llm_provider=RevisionThenAuditProvider()).revise_current_draft(
            state.run_id
        )

    _assert_no_v2_side_effects(store, state.run_id)


def test_revision_agent_rejects_gate_report_wrong_draft_version(tmp_path) -> None:
    store, state = _failed_gate_ready_state(tmp_path)
    gate_path = _quality_path(store, state.run_id)
    gate = _load_json(gate_path)
    gate["draft_version"] = "v2"
    _write_json(gate_path, gate)

    with pytest.raises(ValueError, match="draft_version|不匹配"):
        RevisionLoopService(store, llm_provider=RevisionThenAuditProvider()).revise_current_draft(
            state.run_id
        )

    _assert_no_v2_side_effects(store, state.run_id)


def test_revision_agent_rejects_gate_report_finding_ids_mismatch(tmp_path) -> None:
    store, state = _failed_gate_ready_state(tmp_path)
    gate_path = _quality_path(store, state.run_id)
    gate = _load_json(gate_path)
    gate["blocking_finding_ids"] = ["audit_finding_wrong"]
    _write_json(gate_path, gate)

    with pytest.raises(ValueError, match="finding_ids|不匹配"):
        RevisionLoopService(store, llm_provider=RevisionThenAuditProvider()).revise_current_draft(
            state.run_id
        )

    _assert_no_v2_side_effects(store, state.run_id)


def test_revision_agent_rejects_gate_report_severity_counts_mismatch(tmp_path) -> None:
    store, state = _failed_gate_ready_state(tmp_path)
    gate_path = _quality_path(store, state.run_id)
    gate = _load_json(gate_path)
    gate["severity_counts"]["blocker"] = 999
    _write_json(gate_path, gate)

    with pytest.raises(ValueError, match="severity_counts|不匹配"):
        RevisionLoopService(store, llm_provider=RevisionThenAuditProvider()).revise_current_draft(
            state.run_id
        )

    _assert_no_v2_side_effects(store, state.run_id)


def test_revision_agent_rejects_gate_report_not_require_revision(tmp_path) -> None:
    store, state = _failed_gate_ready_state(tmp_path)
    gate_path = _quality_path(store, state.run_id)
    gate = _load_json(gate_path)
    gate["passed"] = True
    gate["decision"] = "export_docx"
    gate["next_workflow_status"] = "DRAFT_QUALITY_GATE_PASSED"
    gate["next_action"] = "export_docx"
    _write_json(gate_path, gate)
    reloaded = store.load_state(state.run_id)
    reloaded.workflow_status = WorkflowStatus.DRAFT_REVISION_REQUIRED
    reloaded.next_action = NextAction.REVISE_DRAFT
    store.save_state(reloaded)

    with pytest.raises(ValueError, match="未通过|require_revision|不允许修订"):
        RevisionLoopService(store, llm_provider=RevisionThenAuditProvider()).revise_current_draft(
            state.run_id
        )

    _assert_no_v2_side_effects(store, state.run_id)


def test_revision_agent_rejects_gate_report_audit_overall_mismatch(tmp_path) -> None:
    store, state = _failed_gate_ready_state(tmp_path)
    gate_path = _quality_path(store, state.run_id)
    gate = _load_json(gate_path)
    gate["audit_overall_passed"] = True
    _write_json(gate_path, gate)

    with pytest.raises(ValueError, match="audit_overall_passed|不匹配"):
        RevisionLoopService(store, llm_provider=RevisionThenAuditProvider()).revise_current_draft(
            state.run_id
        )

    _assert_no_v2_side_effects(store, state.run_id)


def test_revision_agent_rejects_state_audit_report_result_id_mismatch(tmp_path) -> None:
    store, state = _failed_gate_ready_state(tmp_path)
    reloaded = store.load_state(state.run_id)
    reloaded.audit_report_result_id = "audit_result_wrong"
    store.save_state(reloaded)

    with pytest.raises(ValueError, match="audit_report_result_id|不匹配"):
        RevisionLoopService(store, llm_provider=RevisionThenAuditProvider()).revise_current_draft(
            state.run_id
        )

    _assert_no_v2_side_effects(store, state.run_id)


def test_revision_agent_rejects_state_gate_report_ref_mismatch(tmp_path) -> None:
    store, state = _failed_gate_ready_state(tmp_path)
    reloaded = store.load_state(state.run_id)
    reloaded.draft_quality_gate_report_ref = "drafts/quality_gate_report_v2.json"
    store.save_state(reloaded)

    with pytest.raises(ValueError, match="draft_quality_gate_report_ref|不匹配"):
        RevisionLoopService(store, llm_provider=RevisionThenAuditProvider()).revise_current_draft(
            state.run_id
        )

    _assert_no_v2_side_effects(store, state.run_id)
