import hashlib
import json
from pathlib import Path

import pytest

from docforge_core.agents.audit_agent import AuditAgentService
from docforge_core.agents.figure_slot_planner import FigureSlotPlannerService
from docforge_core.domain.enums import AuditCategory, DraftVersionLabel, NextAction, WorkflowStatus
from docforge_core.io.state_store import StateStore
from docforge_core.llm.base import LLMMessage, LLMProvider, LLMResponse
from docforge_core.llm.mock_provider import MockLLMProvider

from .agent_helpers import product_evidence, reference_evidence
from .test_figure_slot_planner import _draft_ready_state, _figure_path


def _draft_path(store, run_id: str) -> Path:
    return store.data_dir / "runs" / run_id / "drafts" / "draft_v1.json"


def _audit_path(store, run_id: str) -> Path:
    return store.data_dir / "runs" / run_id / "drafts" / "audit_report_v1.json"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


class FailingSaveStateStore(StateStore):
    def save_state(self, state):
        raise RuntimeError("injected save_state failure")


class FailingLLMProvider(LLMProvider):
    def generate_text(
        self,
        messages: list[LLMMessage],
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        raise RuntimeError("semantic verifier unavailable")


class RecordingLLMProvider(MockLLMProvider):
    def __init__(self) -> None:
        super().__init__(json_response={"findings": []})
        self.payloads: list[dict] = []

    def generate_json(
        self,
        messages: list[LLMMessage],
        temperature: float = 0.1,
        max_tokens: int | None = None,
    ) -> dict:
        self.payloads.append(json.loads(messages[1].content))
        return super().generate_json(messages, temperature=temperature, max_tokens=max_tokens)


def _audit_ready_state(tmp_path: Path, *, llm_response: dict | None = None):
    store, state = _draft_ready_state(tmp_path)
    FigureSlotPlannerService(store).plan_figure_slots(state.run_id)
    state = store.load_state(state.run_id)
    provider = MockLLMProvider(json_response=llm_response or {"findings": []})
    return store, state, provider


def _first_section(store, run_id: str) -> dict:
    return _load_json(_draft_path(store, run_id))["chapters"][0]["sections"][0]


def _replace_first_section(store, run_id: str, section: dict) -> None:
    draft_path = _draft_path(store, run_id)
    draft = _load_json(draft_path)
    draft["chapters"][0]["sections"][0] = section
    _write_json(draft_path, draft)


def _run_audit(store, state, provider=None):
    return AuditAgentService(
        store,
        llm_provider=provider or MockLLMProvider(json_response={"findings": []}),
    ).audit_draft(state.run_id)


def _categories(report) -> set[AuditCategory]:
    return {item.category for item in report.findings}


def test_audit_draft_writes_report_and_preserves_inputs(tmp_path) -> None:
    store, state, provider = _audit_ready_state(tmp_path)
    draft_hash = _sha256(_draft_path(store, state.run_id))
    figure_hash = _sha256(_figure_path(store, state.run_id))
    draft_versions = [item.model_dump(mode="json") for item in state.draft_versions]

    report = _run_audit(store, state, provider)

    reloaded = store.load_state(state.run_id)
    assert _audit_path(store, state.run_id).exists()
    assert reloaded.workflow_status == WorkflowStatus.DRAFT_AUDITED
    assert reloaded.next_action == NextAction.RUN_DRAFT_QUALITY_GATE
    assert reloaded.audit_report_ref == "drafts/audit_report_v1.json"
    assert reloaded.audit_report_result_id == report.report_id
    assert _sha256(_draft_path(store, state.run_id)) == draft_hash
    assert _sha256(_figure_path(store, state.run_id)) == figure_hash
    assert [item.model_dump(mode="json") for item in reloaded.draft_versions] == draft_versions


def test_audit_report_records_source_draft_and_figure_hash(tmp_path) -> None:
    store, state, provider = _audit_ready_state(tmp_path)

    report = _run_audit(store, state, provider)
    saved = _load_json(_audit_path(store, state.run_id))

    assert report.source_draft_hash == _sha256(_draft_path(store, state.run_id))
    assert report.source_figure_slots_hash == _sha256(_figure_path(store, state.run_id))
    assert saved["source_draft_hash"] == _sha256(_draft_path(store, state.run_id))
    assert saved["source_figure_slots_hash"] == _sha256(_figure_path(store, state.run_id))


def test_audit_draft_rejects_wrong_workflow_status(tmp_path) -> None:
    store, state, provider = _audit_ready_state(tmp_path)
    state.workflow_status = WorkflowStatus.PLAN_GATE_PASSED
    store.save_state(state)

    with pytest.raises(ValueError, match="AuditAgent"):
        _run_audit(store, state, provider)

    assert not _audit_path(store, state.run_id).exists()
    assert store.load_state(state.run_id).workflow_status == WorkflowStatus.PLAN_GATE_PASSED


def test_audit_draft_rejects_wrong_next_action(tmp_path) -> None:
    store, state, provider = _audit_ready_state(tmp_path)
    state.next_action = NextAction.STOP
    store.save_state(state)

    with pytest.raises(ValueError, match="AuditAgent"):
        _run_audit(store, state, provider)

    reloaded = store.load_state(state.run_id)
    assert not _audit_path(store, state.run_id).exists()
    assert reloaded.next_action == NextAction.STOP


def test_audit_draft_requires_draft_v1_file(tmp_path) -> None:
    store, state, provider = _audit_ready_state(tmp_path)
    _draft_path(store, state.run_id).unlink()

    with pytest.raises(ValueError, match="draft_v1"):
        _run_audit(store, state, provider)

    assert not _audit_path(store, state.run_id).exists()
    assert store.load_state(state.run_id).workflow_status == WorkflowStatus.FIGURE_SLOTS_PLANNED


def test_audit_draft_requires_figure_slots_file(tmp_path) -> None:
    store, state, provider = _audit_ready_state(tmp_path)
    _figure_path(store, state.run_id).unlink()

    with pytest.raises(ValueError, match="figure_slots"):
        _run_audit(store, state, provider)

    assert not _audit_path(store, state.run_id).exists()
    assert store.load_state(state.run_id).workflow_status == WorkflowStatus.FIGURE_SLOTS_PLANNED


def test_audit_draft_reports_missing_citation_evidence_id_as_blocker(tmp_path) -> None:
    store, state, provider = _audit_ready_state(tmp_path)
    section = _first_section(store, state.run_id)
    section["citations"] = [{"evidence_id": "ev_missing", "quote": "missing quote"}]
    _replace_first_section(store, state.run_id, section)

    report = _run_audit(store, state, provider)

    assert AuditCategory.EVIDENCE_ID_NOT_FOUND in _categories(report)
    assert report.overall_passed is False
    assert report.summary.blocker_count > 0


def test_audit_draft_reports_bad_chapters_container_as_blocker(tmp_path) -> None:
    store, state, provider = _audit_ready_state(tmp_path)
    draft = _load_json(_draft_path(store, state.run_id))
    draft["chapters"] = "bad chapters"
    _write_json(_draft_path(store, state.run_id), draft)

    report = _run_audit(store, state, provider)

    assert AuditCategory.DRAFT_SCHEMA_INVALID in _categories(report)
    assert report.summary.blocker_count > 0
    assert report.overall_passed is False


@pytest.mark.parametrize("bad_chapters", [None, 1])
def test_audit_draft_reports_non_list_chapters_without_crashing(tmp_path, bad_chapters) -> None:
    store, state, provider = _audit_ready_state(tmp_path)
    draft = _load_json(_draft_path(store, state.run_id))
    draft["chapters"] = bad_chapters
    _write_json(_draft_path(store, state.run_id), draft)

    report = _run_audit(store, state, provider)

    reloaded = store.load_state(state.run_id)
    assert _audit_path(store, state.run_id).exists()
    assert AuditCategory.DRAFT_SCHEMA_INVALID in _categories(report)
    assert report.summary.blocker_count > 0
    assert report.overall_passed is False
    assert reloaded.workflow_status == WorkflowStatus.DRAFT_AUDITED
    assert reloaded.next_action == NextAction.RUN_DRAFT_QUALITY_GATE


def test_audit_draft_reports_bad_chapter_object_as_blocker(tmp_path) -> None:
    store, state, provider = _audit_ready_state(tmp_path)
    draft = _load_json(_draft_path(store, state.run_id))
    draft["chapters"] = ["bad chapter"]
    _write_json(_draft_path(store, state.run_id), draft)

    report = _run_audit(store, state, provider)

    assert AuditCategory.DRAFT_SCHEMA_INVALID in _categories(report)
    assert report.overall_passed is False


def test_audit_draft_reports_bad_chapter_sections_as_blocker(tmp_path) -> None:
    store, state, provider = _audit_ready_state(tmp_path)
    draft = _load_json(_draft_path(store, state.run_id))
    draft["chapters"][0]["sections"] = "bad sections"
    _write_json(_draft_path(store, state.run_id), draft)

    report = _run_audit(store, state, provider)

    assert AuditCategory.DRAFT_SCHEMA_INVALID in _categories(report)
    assert report.overall_passed is False


@pytest.mark.parametrize("bad_sections", [None, 1])
def test_audit_draft_reports_non_list_chapter_sections_without_crashing(tmp_path, bad_sections) -> None:
    store, state, provider = _audit_ready_state(tmp_path)
    draft = _load_json(_draft_path(store, state.run_id))
    draft["chapters"][0]["sections"] = bad_sections
    _write_json(_draft_path(store, state.run_id), draft)

    report = _run_audit(store, state, provider)

    assert _audit_path(store, state.run_id).exists()
    assert AuditCategory.DRAFT_SCHEMA_INVALID in _categories(report)
    assert report.summary.blocker_count > 0
    assert report.overall_passed is False


def test_audit_draft_reports_bad_section_object_as_blocker(tmp_path) -> None:
    store, state, provider = _audit_ready_state(tmp_path)
    draft = _load_json(_draft_path(store, state.run_id))
    draft["chapters"][0]["sections"] = ["bad section"]
    _write_json(_draft_path(store, state.run_id), draft)

    report = _run_audit(store, state, provider)

    assert AuditCategory.DRAFT_SCHEMA_INVALID in _categories(report)
    assert report.overall_passed is False


def test_audit_draft_reports_duplicate_section_id_as_blocker(tmp_path) -> None:
    store, state, provider = _audit_ready_state(tmp_path)
    draft = _load_json(_draft_path(store, state.run_id))
    first = draft["chapters"][0]["sections"][0]
    duplicate = dict(first)
    draft["chapters"][0]["sections"].append(duplicate)
    _write_json(_draft_path(store, state.run_id), draft)

    report = _run_audit(store, state, provider)

    assert AuditCategory.DRAFT_SCHEMA_INVALID in _categories(report)
    assert report.overall_passed is False


def test_audit_draft_reports_bad_evidence_ids_used_schema_as_blocker(tmp_path) -> None:
    store, state, provider = _audit_ready_state(tmp_path)
    section = _first_section(store, state.run_id)
    section["evidence_ids_used"] = "ev_product"
    _replace_first_section(store, state.run_id, section)

    report = _run_audit(store, state, provider)

    assert AuditCategory.DRAFT_SCHEMA_INVALID in _categories(report)
    assert report.overall_passed is False


@pytest.mark.parametrize("bad_path", [None, {"bad": "path"}, 123, True])
def test_audit_draft_reports_bad_section_path_without_crashing(tmp_path, bad_path) -> None:
    store, state, provider = _audit_ready_state(tmp_path)
    section = _first_section(store, state.run_id)
    section["section_path"] = bad_path
    _replace_first_section(store, state.run_id, section)

    report = _run_audit(store, state, provider)

    assert _audit_path(store, state.run_id).exists()
    assert AuditCategory.DRAFT_SCHEMA_INVALID in _categories(report)
    assert report.summary.blocker_count > 0
    assert report.overall_passed is False


def test_audit_draft_reports_bad_citations_schema_as_blocker(tmp_path) -> None:
    store, state, provider = _audit_ready_state(tmp_path)
    section = _first_section(store, state.run_id)
    section["citations"] = "bad citations"
    _replace_first_section(store, state.run_id, section)

    report = _run_audit(store, state, provider)

    assert AuditCategory.DRAFT_SCHEMA_INVALID in _categories(report)
    assert report.overall_passed is False


def test_audit_draft_reports_missing_citation_quote_schema_as_blocker(tmp_path) -> None:
    store, state, provider = _audit_ready_state(tmp_path)
    section = _first_section(store, state.run_id)
    section["citations"] = [{"evidence_id": "ev_product"}]
    _replace_first_section(store, state.run_id, section)

    report = _run_audit(store, state, provider)

    assert AuditCategory.DRAFT_SCHEMA_INVALID in _categories(report)
    assert report.overall_passed is False


def test_audit_draft_reports_missing_citation_evidence_id_schema_as_blocker(tmp_path) -> None:
    store, state, provider = _audit_ready_state(tmp_path)
    section = _first_section(store, state.run_id)
    section["citations"] = [{"quote": "当前版本明确支持数据集管理能力"}]
    _replace_first_section(store, state.run_id, section)

    report = _run_audit(store, state, provider)

    assert AuditCategory.DRAFT_SCHEMA_INVALID in _categories(report)
    assert report.overall_passed is False


def test_audit_draft_reports_quote_not_found_as_blocker(tmp_path) -> None:
    store, state, provider = _audit_ready_state(tmp_path)
    section = _first_section(store, state.run_id)
    section["citations"] = [{"evidence_id": "ev_product", "quote": "原文中不存在的 quote"}]
    _replace_first_section(store, state.run_id, section)

    report = _run_audit(store, state, provider)

    assert AuditCategory.CITATION_QUOTE_NOT_FOUND in _categories(report)
    assert report.overall_passed is False


def test_audit_draft_accepts_quote_from_safe_content_ref(tmp_path) -> None:
    store, state, provider = _audit_ready_state(tmp_path)
    quote = "这是只存在于 content_ref 文件里的产品原文片段"
    parsed_dir = store.data_dir / "runs" / state.run_id / "parsed"
    parsed_dir.mkdir(parents=True, exist_ok=True)
    (parsed_dir / "chunk_001.txt").write_text(f"前缀\n{quote}\n后缀", encoding="utf-8")
    state.evidence_map[0].summary = "摘要不包含目标 quote"
    state.evidence_map[0].content_ref = "parsed/chunk_001.txt"
    store.save_state(state)
    draft = _load_json(_draft_path(store, state.run_id))
    for chapter in draft["chapters"]:
        for section in chapter["sections"]:
            section["citations"] = [{"evidence_id": "ev_product", "quote": quote}]
            section["evidence_ids_used"] = ["ev_product"]
    _write_json(_draft_path(store, state.run_id), draft)

    report = _run_audit(store, state, provider)

    assert AuditCategory.CITATION_QUOTE_NOT_FOUND not in _categories(report)
    assert report.overall_passed is True


def test_audit_draft_rejects_content_ref_path_traversal(tmp_path) -> None:
    store, state, provider = _audit_ready_state(tmp_path)
    quote = "这是越界文件里的伪 quote"
    evil_path = store.data_dir / "evil.txt"
    evil_path.write_text(quote, encoding="utf-8")
    state.evidence_map[0].summary = "摘要不包含目标 quote"
    state.evidence_map[0].content_ref = "../../evil.txt"
    store.save_state(state)
    section = _first_section(store, state.run_id)
    section["citations"] = [{"evidence_id": "ev_product", "quote": quote}]
    _replace_first_section(store, state.run_id, section)

    report = _run_audit(store, state, provider)

    assert AuditCategory.CITATION_QUOTE_NOT_FOUND in _categories(report)
    assert report.overall_passed is False


def test_audit_draft_does_not_accept_quote_from_metadata(tmp_path) -> None:
    store, state, provider = _audit_ready_state(tmp_path)
    quote = "这是只存在 metadata 里的伪 quote"
    state.evidence_map[0].summary = "摘要不包含目标 quote"
    state.evidence_map[0].extracted_facts = []
    state.evidence_map[0].notes = ""
    state.evidence_map[0].metadata = {"some_key": quote}
    store.save_state(state)
    section = _first_section(store, state.run_id)
    section["citations"] = [{"evidence_id": "ev_product", "quote": quote}]
    _replace_first_section(store, state.run_id, section)

    report = _run_audit(store, state, provider)

    assert AuditCategory.CITATION_QUOTE_NOT_FOUND in _categories(report)
    assert report.overall_passed is False


def test_audit_draft_reports_citation_out_of_section_plan_as_blocker(tmp_path) -> None:
    store, state, provider = _audit_ready_state(tmp_path)
    state.evidence_map.append(
        product_evidence(
            evidence_id="ev_other",
            source_id="other_source",
            summary="其他证据原文",
        )
    )
    store.save_state(state)
    section = _first_section(store, state.run_id)
    section["citations"] = [{"evidence_id": "ev_other", "quote": "其他证据原文"}]
    _replace_first_section(store, state.run_id, section)

    report = _run_audit(store, state, provider)

    assert AuditCategory.CITATION_OUT_OF_SECTION_PLAN in _categories(report)
    assert report.overall_passed is False


def test_audit_draft_reports_reference_style_used_as_fact(tmp_path) -> None:
    store, state, provider = _audit_ready_state(tmp_path)
    ref = reference_evidence(evidence_id="ev_ref_001", summary="参考软著引用")
    state.evidence_map.append(ref)
    state.section_plan[0].required_evidence_ids.append("ev_ref_001")
    assert state.outline is not None
    state.outline.chapters[0]["sections"][0]["required_evidence_ids"].append("ev_ref_001")
    store.save_state(state)
    section = _first_section(store, state.run_id)
    section["required_evidence_ids"].append("ev_ref_001")
    section["citations"] = [{"evidence_id": "ev_ref_001", "quote": "参考软著引用"}]
    _replace_first_section(store, state.run_id, section)

    report = _run_audit(store, state, provider)

    assert AuditCategory.REFERENCE_STYLE_USED_AS_FACT in _categories(report)
    assert report.overall_passed is False


def test_audit_draft_reports_figure_slot_claims_existing_image(tmp_path) -> None:
    store, state, provider = _audit_ready_state(tmp_path)
    figures = _load_json(_figure_path(store, state.run_id))
    figures["figure_slots"][0]["existing_screenshot"] = "shot.png"
    _write_json(_figure_path(store, state.run_id), figures)

    report = _run_audit(store, state, provider)

    assert AuditCategory.FIGURE_SLOT_CLAIMS_EXISTING_IMAGE in _categories(report)
    assert report.overall_passed is False


def test_audit_draft_reports_figure_slot_section_not_found(tmp_path) -> None:
    store, state, provider = _audit_ready_state(tmp_path)
    figures = _load_json(_figure_path(store, state.run_id))
    figures["figure_slots"][0]["section_id"] = "sec_missing"
    _write_json(_figure_path(store, state.run_id), figures)

    report = _run_audit(store, state, provider)

    assert AuditCategory.FIGURE_SLOT_SECTION_NOT_FOUND in _categories(report)


@pytest.mark.parametrize("bad_path", [None, {"bad": "path"}, 123, True])
def test_audit_draft_reports_bad_figure_slot_path_without_crashing(tmp_path, bad_path) -> None:
    store, state, provider = _audit_ready_state(tmp_path)
    figures = _load_json(_figure_path(store, state.run_id))
    figures["figure_slots"][0]["section_id"] = "missing_section"
    figures["figure_slots"][0]["section_path"] = bad_path
    _write_json(_figure_path(store, state.run_id), figures)

    report = _run_audit(store, state, provider)

    assert _audit_path(store, state.run_id).exists()
    assert AuditCategory.FIGURE_SLOT_INVALID in _categories(report)
    assert AuditCategory.FIGURE_SLOT_SECTION_NOT_FOUND in _categories(report)
    assert report.overall_passed is False


@pytest.mark.parametrize("bad_slots", [None, 1, True])
def test_audit_draft_reports_non_list_figure_slots_without_crashing(tmp_path, bad_slots) -> None:
    store, state, provider = _audit_ready_state(tmp_path)
    figures = _load_json(_figure_path(store, state.run_id))
    figures["figure_slots"] = bad_slots
    _write_json(_figure_path(store, state.run_id), figures)

    report = _run_audit(store, state, provider)

    assert _audit_path(store, state.run_id).exists()
    assert AuditCategory.FIGURE_SLOT_INVALID in _categories(report)
    assert report.summary.blocker_count > 0
    assert report.overall_passed is False


@pytest.mark.parametrize("version_action", ["bad", "missing"])
def test_audit_draft_reports_bad_or_missing_version_label(tmp_path, version_action) -> None:
    store, state, provider = _audit_ready_state(tmp_path)
    draft = _load_json(_draft_path(store, state.run_id))
    if version_action == "bad":
        draft["version_label"] = "bad_version"
    else:
        draft.pop("version_label")
    _write_json(_draft_path(store, state.run_id), draft)

    report = _run_audit(store, state, provider)

    reloaded = store.load_state(state.run_id)
    assert _audit_path(store, state.run_id).exists()
    assert AuditCategory.DRAFT_SCHEMA_INVALID in _categories(report)
    assert report.summary.blocker_count > 0
    assert report.overall_passed is False
    assert reloaded.workflow_status == WorkflowStatus.DRAFT_AUDITED
    assert reloaded.next_action == NextAction.RUN_DRAFT_QUALITY_GATE


def test_audit_draft_accepts_valid_semantic_llm_finding(tmp_path) -> None:
    store, state, _provider = _audit_ready_state(tmp_path)
    section = _first_section(store, state.run_id)
    quote = section["citations"][0]["quote"]
    claim = section["content"][: min(12, len(section["content"]))]
    provider = MockLLMProvider(
        json_response={
            "findings": [
                {
                    "severity": "blocker",
                    "category": "planned_written_as_current",
                    "section_id": section["section_id"],
                    "message": "planned capability written as current",
                    "claim_text": claim,
                    "evidence_id": "ev_product",
                    "quote": quote,
                    "recommendation": "revise claim",
                    "confidence": 0.9,
                }
            ]
        }
    )

    report = _run_audit(store, state, provider)

    assert AuditCategory.PLANNED_WRITTEN_AS_CURRENT in _categories(report)
    assert any(item.detector == "semantic_llm" for item in report.findings)
    assert report.overall_passed is False


def test_audit_draft_llm_payload_contains_feature_policy_projection(tmp_path) -> None:
    store, state, _provider = _audit_ready_state(tmp_path)
    provider = RecordingLLMProvider()

    _run_audit(store, state, provider)

    payload = provider.payloads[0]
    feature_policy = payload["document_constraints"]["feature_policy"]
    assert "current_capabilities" in feature_policy
    assert "planned_capabilities" in feature_policy
    assert "unknown_capabilities" in feature_policy
    assert "unsupported_or_rejected_features" in feature_policy
    assert "forbidden_as_current_feature_names" in feature_policy
    serialized = json.dumps(payload, ensure_ascii=False)
    assert "reference_style 原文" not in serialized
    assert "OCR" not in serialized
    assert "视觉" not in serialized


def test_audit_draft_reports_planned_capability_in_section_plan(tmp_path) -> None:
    store, state, provider = _audit_ready_state(tmp_path)
    assert state.frozen_doc_plan is not None
    state.frozen_doc_plan.feature_policy["planned_capabilities"] = [
        {"capability_id": "cap_planned", "name": "模型训练"}
    ]
    state.section_plan[0].required_capability_ids = ["cap_planned"]
    store.save_state(state)

    report = _run_audit(store, state, provider)

    assert AuditCategory.PLANNED_WRITTEN_AS_CURRENT in _categories(report)
    assert report.overall_passed is False


def test_audit_draft_reports_unknown_capability_in_section_plan(tmp_path) -> None:
    store, state, provider = _audit_ready_state(tmp_path)
    assert state.frozen_doc_plan is not None
    state.frozen_doc_plan.feature_policy["unknown_capabilities"] = [
        {"capability_id": "cap_unknown", "name": "未知能力"}
    ]
    state.section_plan[0].required_capability_ids = ["cap_unknown"]
    store.save_state(state)

    report = _run_audit(store, state, provider)

    assert AuditCategory.UNKNOWN_WRITTEN_AS_CURRENT in _categories(report)
    assert report.overall_passed is False


def test_audit_draft_reports_unsupported_or_rejected_capability_in_section_plan(tmp_path) -> None:
    store, state, provider = _audit_ready_state(tmp_path)
    assert state.frozen_doc_plan is not None
    state.frozen_doc_plan.feature_policy["unsupported_or_rejected_features"] = [
        {"capability_id": "cap_unsup", "name": "不支持能力"}
    ]
    state.section_plan[0].required_capability_ids = ["cap_unsup"]
    store.save_state(state)

    report = _run_audit(store, state, provider)

    assert AuditCategory.UNSUPPORTED_CAPABILITY_CLAIM in _categories(report)
    assert report.overall_passed is False


def test_audit_draft_reports_legacy_unsupported_capability_in_section_plan(tmp_path) -> None:
    store, state, provider = _audit_ready_state(tmp_path)
    assert state.frozen_doc_plan is not None
    state.frozen_doc_plan.feature_policy["unsupported_capabilities"] = [
        {"capability_id": "cap_unsup_legacy", "name": "旧字段不支持能力"}
    ]
    state.section_plan[0].required_capability_ids = ["cap_unsup_legacy"]
    store.save_state(state)

    report = _run_audit(store, state, provider)

    assert AuditCategory.UNSUPPORTED_CAPABILITY_CLAIM in _categories(report)
    assert report.overall_passed is False


def test_audit_draft_reports_needs_human_confirmation_section(tmp_path) -> None:
    store, state, provider = _audit_ready_state(tmp_path)
    state.section_plan[0].needs_human_confirmation = True
    store.save_state(state)

    report = _run_audit(store, state, provider)

    assert any(item.severity.value == "major" for item in report.findings)
    assert report.findings


def test_audit_draft_reports_software_identity_mismatch(tmp_path) -> None:
    store, state, provider = _audit_ready_state(tmp_path)
    draft = _load_json(_draft_path(store, state.run_id))
    draft["software_identity"] = {
        "target_product_name": "完全错误的软件名称",
        "version": "V1.0",
    }
    _write_json(_draft_path(store, state.run_id), draft)

    report = _run_audit(store, state, provider)

    assert AuditCategory.SOFTWARE_IDENTITY_MISMATCH in _categories(report)
    assert report.overall_passed is False


def test_audit_draft_reports_software_version_mismatch(tmp_path) -> None:
    store, state, provider = _audit_ready_state(tmp_path)
    draft = _load_json(_draft_path(store, state.run_id))
    draft["software_identity"] = {
        "target_product_name": "墨衡测试软件",
        "version": "V9.9",
    }
    _write_json(_draft_path(store, state.run_id), draft)

    report = _run_audit(store, state, provider)

    assert AuditCategory.SOFTWARE_VERSION_MISMATCH in _categories(report)
    assert any(item.severity.value in {"major", "blocker"} for item in report.findings)


def test_audit_draft_missing_software_identity_is_non_blocking_finding(tmp_path) -> None:
    store, state, provider = _audit_ready_state(tmp_path)

    report = _run_audit(store, state, provider)

    finding = next(
        item for item in report.findings if item.category == AuditCategory.SOFTWARE_IDENTITY_MISSING
    )
    assert finding.severity.value in {"suggestion", "minor"}
    assert report.summary.blocker_count == 0


def test_audit_draft_turns_illegal_llm_evidence_id_into_validator_blocker(tmp_path) -> None:
    store, state, _provider = _audit_ready_state(tmp_path)
    section = _first_section(store, state.run_id)
    provider = MockLLMProvider(
        json_response={
            "findings": [
                {
                    "severity": "blocker",
                    "category": "planned_written_as_current",
                    "section_id": section["section_id"],
                    "message": "bad evidence id",
                    "claim_text": section["content"][:8],
                    "evidence_id": "ev_not_in_section_plan",
                    "quote": "x",
                    "recommendation": "revise",
                    "confidence": 0.9,
                }
            ]
        }
    )

    report = _run_audit(store, state, provider)

    assert AuditCategory.SEMANTIC_VERIFIER_FAILED in _categories(report)
    assert any(item.detector == "validator" for item in report.findings)
    assert report.overall_passed is False


def test_audit_draft_turns_llm_quote_without_evidence_id_into_validator_blocker(tmp_path) -> None:
    store, state, _provider = _audit_ready_state(tmp_path)
    section = _first_section(store, state.run_id)
    provider = MockLLMProvider(
        json_response={
            "findings": [
                {
                    "severity": "major",
                    "category": "claim_not_supported_by_quote",
                    "section_id": section["section_id"],
                    "message": "claim unsupported",
                    "claim_text": section["content"][:8],
                    "evidence_id": None,
                    "quote": "一个没有 evidence_id 的 quote",
                    "recommendation": "revise",
                    "confidence": 0.8,
                }
            ]
        }
    )

    report = _run_audit(store, state, provider)

    assert AuditCategory.SEMANTIC_VERIFIER_FAILED in _categories(report)
    assert any(item.detector == "validator" for item in report.findings)
    assert report.overall_passed is False


def test_audit_draft_accepts_llm_evidence_id_without_quote_for_style_finding(tmp_path) -> None:
    store, state, _provider = _audit_ready_state(tmp_path)
    section = _first_section(store, state.run_id)
    responses = [
        {
                "findings": [
                    {
                        "severity": "minor",
                        "category": "style_deviation",
                        "section_id": section["section_id"],
                        "message": "style deviation",
                        "claim_text": section["content"][:8],
                        "evidence_id": "ev_product",
                        "quote": None,
                        "recommendation": "adjust style",
                        "confidence": 0.7,
                    }
                ]
            }
    ]
    responses.extend({"findings": []} for _ in range(max(0, len(state.section_plan) - 1)))
    provider = MockLLMProvider(json_responses=responses)

    report = _run_audit(store, state, provider)

    assert AuditCategory.STYLE_DEVIATION in _categories(report)
    assert any(
        item.category == AuditCategory.STYLE_DEVIATION and item.detector == "semantic_llm"
        for item in report.findings
    )
    assert AuditCategory.SEMANTIC_VERIFIER_FAILED not in _categories(report)


def test_audit_draft_llm_failure_generates_fail_closed_report(tmp_path) -> None:
    store, state, _provider = _audit_ready_state(tmp_path)

    report = _run_audit(store, state, FailingLLMProvider())

    reloaded = store.load_state(state.run_id)
    assert _audit_path(store, state.run_id).exists()
    assert AuditCategory.SEMANTIC_VERIFIER_FAILED in _categories(report)
    assert report.overall_passed is False
    assert reloaded.workflow_status == WorkflowStatus.DRAFT_AUDITED
    assert reloaded.next_action == NextAction.RUN_DRAFT_QUALITY_GATE


def test_audit_draft_does_not_modify_draft_or_figure_slots(tmp_path) -> None:
    store, state, provider = _audit_ready_state(tmp_path)
    draft_before = _load_json(_draft_path(store, state.run_id))
    figure_before = _load_json(_figure_path(store, state.run_id))
    draft_hash = _sha256(_draft_path(store, state.run_id))
    figure_hash = _sha256(_figure_path(store, state.run_id))

    _run_audit(store, state, provider)

    draft_after = _load_json(_draft_path(store, state.run_id))
    assert _sha256(_draft_path(store, state.run_id)) == draft_hash
    assert _sha256(_figure_path(store, state.run_id)) == figure_hash
    assert _load_json(_figure_path(store, state.run_id)) == figure_before
    assert draft_after == draft_before
    assert draft_after["chapters"][0]["sections"][0]["content"] == draft_before["chapters"][0]["sections"][0]["content"]
    assert draft_after["chapters"][0]["sections"][0]["evidence_ids_used"] == draft_before["chapters"][0]["sections"][0]["evidence_ids_used"]
    assert draft_after["chapters"][0]["sections"][0]["citations"] == draft_before["chapters"][0]["sections"][0]["citations"]


def test_audit_draft_removes_orphan_report_when_save_state_fails(tmp_path) -> None:
    store, state, provider = _audit_ready_state(tmp_path)
    failing_store = FailingSaveStateStore(data_dir=store.data_dir)

    with pytest.raises(RuntimeError, match="save_state failure"):
        AuditAgentService(failing_store, llm_provider=provider).audit_draft(state.run_id)

    reloaded = store.load_state(state.run_id)
    assert not _audit_path(store, state.run_id).exists()
    assert not (_audit_path(store, state.run_id).with_suffix(".json.tmp")).exists()
    assert reloaded.workflow_status == WorkflowStatus.FIGURE_SLOTS_PLANNED
    assert reloaded.audit_report_ref is None
    assert reloaded.audit_report_result_id is None


def test_audit_draft_rejects_stale_unrecorded_audit_report(tmp_path) -> None:
    store, state, provider = _audit_ready_state(tmp_path)
    stale = {"stale": True}
    _write_json(_audit_path(store, state.run_id), stale)

    with pytest.raises(ValueError, match="stale|未被 state 承认"):
        _run_audit(store, state, provider)

    assert _load_json(_audit_path(store, state.run_id)) == stale
    assert store.load_state(state.run_id).workflow_status == WorkflowStatus.FIGURE_SLOTS_PLANNED


def test_audit_draft_rejects_repeated_execution_after_audited(tmp_path) -> None:
    store, state, provider = _audit_ready_state(tmp_path)
    _run_audit(store, state, provider)
    audited = store.load_state(state.run_id)

    with pytest.raises(ValueError, match="AuditAgent"):
        _run_audit(store, audited, provider)

    assert store.load_state(state.run_id).workflow_status == WorkflowStatus.DRAFT_AUDITED
    assert store.load_state(state.run_id).draft_versions[0].version_label == DraftVersionLabel.V1
