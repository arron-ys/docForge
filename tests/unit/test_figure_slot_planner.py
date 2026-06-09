import hashlib
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from docforge_core.agents.figure_slot_planner import (
    FigureSlotPlannerService,
    FigureSlotValidator,
)
from docforge_core.agents.outline_agent import OutlineAgent
from docforge_core.agents.outline_traversal import iter_outline_sections
from docforge_core.agents.writer_agent import WriterAgent
from docforge_core.domain.enums import (
    DraftVersionLabel,
    EvidenceType,
    GateType,
    NextAction,
    WorkflowStatus,
)
from docforge_core.domain.schemas import (
    FigureSlotResult,
    QualityGateReport,
)
from docforge_core.io.state_store import StateStore

from .agent_helpers import product_evidence
from .outline_helpers import SafeWritingPlanSafetyVerifier, frozen_plan_state
from .test_writer_agent import FakeSectionWriterProvider


def _draft_path(store, run_id: str) -> Path:
    return store.data_dir / "runs" / run_id / "drafts" / "draft_v1.json"


def _figure_path(store, run_id: str) -> Path:
    return store.data_dir / "runs" / run_id / "drafts" / "figure_slots_v1.json"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class FailingSaveStateStore(StateStore):
    def save_state(self, state):
        raise RuntimeError("injected save_state failure")


def _draft_ready_state(tmp_path: Path):
    store, state = frozen_plan_state(tmp_path)
    state.evidence_map = [product_evidence(summary="当前版本明确支持数据集管理能力")]
    store.save_state(state)
    state = OutlineAgent(
        store,
        writing_plan_safety_verifier=SafeWritingPlanSafetyVerifier(),
    ).create_outline(state.run_id)
    assert state.outline is not None
    state.workflow_status = WorkflowStatus.PLAN_GATE_PASSED
    state.next_action = NextAction.WRITE_DRAFT
    state.plan_quality_gate_passed = True
    state.plan_quality_gate_report = QualityGateReport(
        gate_type=GateType.PLAN_QUALITY_GATE,
        target_id=state.outline.outline_id,
        passed=True,
        next_action=NextAction.WRITE_DRAFT,
    )
    store.save_state(state)
    state = WriterAgent(store, llm_provider=FakeSectionWriterProvider()).write_v1_draft(
        state.run_id
    )
    return store, state


def _first_draft_section(store, run_id: str) -> dict:
    draft = json.loads(_draft_path(store, run_id).read_text(encoding="utf-8"))
    return draft["chapters"][0]["sections"][0]


def _write_first_draft_section(store, run_id: str, section: dict) -> None:
    draft_path = _draft_path(store, run_id)
    draft = json.loads(draft_path.read_text(encoding="utf-8"))
    draft["chapters"][0]["sections"][0] = section
    draft_path.write_text(json.dumps(draft, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _replace_first_section_metadata(
    store,
    state,
    *,
    section_title: str | None = None,
    required_evidence_ids: list[str] | None = None,
    required_capability_ids: list[str] | None = None,
    required_fact_ids: list[str] | None = None,
) -> None:
    assert state.outline is not None
    plan = state.section_plan[0]
    outline_section = state.outline.chapters[0]["sections"][0]
    draft_section = _first_draft_section(store, state.run_id)

    if section_title is not None:
        plan.section_title = section_title
        plan.section_path = [plan.chapter_title, section_title]
        outline_section["title"] = section_title
        draft_section["section_title"] = section_title
        draft_section["section_path"] = plan.section_path
    if required_evidence_ids is not None:
        plan.required_evidence_ids = required_evidence_ids
        outline_section["required_evidence_ids"] = required_evidence_ids
        draft_section["required_evidence_ids"] = required_evidence_ids
    if required_capability_ids is not None:
        plan.required_capability_ids = required_capability_ids
        outline_section["required_capability_ids"] = required_capability_ids
        draft_section["required_capability_ids"] = required_capability_ids
    if required_fact_ids is not None:
        plan.required_fact_ids = required_fact_ids
        outline_section["required_fact_ids"] = required_fact_ids
        draft_section["required_fact_ids"] = required_fact_ids

    store.save_state(state)
    _write_first_draft_section(store, state.run_id, draft_section)


def _clear_all_grounded_content(store, state) -> None:
    assert state.outline is not None
    for plan in state.section_plan:
        plan.required_evidence_ids = []
        plan.required_capability_ids = []
        plan.required_fact_ids = []
    for node in iter_outline_sections(state.outline):
        node.section["required_evidence_ids"] = []
        node.section["required_capability_ids"] = []
        node.section["required_fact_ids"] = []
    store.save_state(state)

    draft_path = _draft_path(store, state.run_id)
    draft = json.loads(draft_path.read_text(encoding="utf-8"))
    for chapter in draft["chapters"]:
        for section in chapter["sections"]:
            section["required_evidence_ids"] = []
            section["required_capability_ids"] = []
            section["required_fact_ids"] = []
    draft_path.write_text(json.dumps(draft, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def test_plan_figure_slots_writes_result_and_preserves_draft_v1(tmp_path) -> None:
    store, state = _draft_ready_state(tmp_path)
    draft_before = json.loads(_draft_path(store, state.run_id).read_text(encoding="utf-8"))
    draft_hash_before = _sha256(_draft_path(store, state.run_id))
    draft_versions_before = [item.model_dump(mode="json") for item in state.draft_versions]

    result = FigureSlotPlannerService(store).plan_figure_slots(state.run_id)

    reloaded = store.load_state(state.run_id)
    assert reloaded.workflow_status == WorkflowStatus.FIGURE_SLOTS_PLANNED
    assert reloaded.next_action == NextAction.AUDIT_DRAFT
    assert reloaded.figure_slots_ref == "drafts/figure_slots_v1.json"
    assert reloaded.figure_slots_result_id == result.result_id
    assert [item.model_dump(mode="json") for item in reloaded.draft_versions] == draft_versions_before
    assert _sha256(_draft_path(store, state.run_id)) == draft_hash_before
    assert json.loads(_draft_path(store, state.run_id).read_text(encoding="utf-8")) == draft_before

    saved = json.loads(_figure_path(store, state.run_id).read_text(encoding="utf-8"))
    assert saved["result_id"] == result.result_id
    assert saved["draft_version"] == "v1"
    assert saved["source_draft_ref"] == "drafts/draft_v1.json"
    assert saved["summary"]["total_slots"] == len(saved["figure_slots"])
    assert saved["summary"]["missing_slots"] == len(saved["figure_slots"])
    assert saved["figure_slots"]
    assert all(slot["status"] == "missing" for slot in saved["figure_slots"])
    assert all("screenshot_file_path" not in slot for slot in saved["figure_slots"])
    assert all("screenshot_source_id" not in slot for slot in saved["figure_slots"])


def test_plan_figure_slots_fail_closed_when_status_is_not_draft_created(tmp_path) -> None:
    store, state = _draft_ready_state(tmp_path)
    state.workflow_status = WorkflowStatus.PLAN_GATE_PASSED
    state.next_action = NextAction.WRITE_DRAFT
    store.save_state(state)

    with pytest.raises(ValueError, match="DRAFT_V1_CREATED"):
        FigureSlotPlannerService(store).plan_figure_slots(state.run_id)

    reloaded = store.load_state(state.run_id)
    assert reloaded.workflow_status == WorkflowStatus.PLAN_GATE_PASSED
    assert reloaded.figure_slots_ref is None
    assert reloaded.figure_slots_result_id is None
    assert not _figure_path(store, state.run_id).exists()


def test_plan_figure_slots_fail_closed_when_next_action_is_wrong(tmp_path) -> None:
    store, state = _draft_ready_state(tmp_path)
    state.next_action = NextAction.STOP
    store.save_state(state)

    with pytest.raises(ValueError, match="PLAN_FIGURE_SLOTS"):
        FigureSlotPlannerService(store).plan_figure_slots(state.run_id)

    reloaded = store.load_state(state.run_id)
    assert reloaded.workflow_status == WorkflowStatus.DRAFT_V1_CREATED
    assert reloaded.next_action == NextAction.STOP
    assert reloaded.figure_slots_ref is None
    assert reloaded.figure_slots_result_id is None
    assert not _figure_path(store, state.run_id).exists()


def test_plan_figure_slots_fail_closed_when_draft_missing(tmp_path) -> None:
    store, state = _draft_ready_state(tmp_path)
    _draft_path(store, state.run_id).unlink()

    with pytest.raises(FileNotFoundError, match="draft_v1.json"):
        FigureSlotPlannerService(store).plan_figure_slots(state.run_id)

    reloaded = store.load_state(state.run_id)
    assert reloaded.workflow_status == WorkflowStatus.DRAFT_V1_CREATED
    assert reloaded.figure_slots_ref is None
    assert reloaded.figure_slots_result_id is None
    assert not _figure_path(store, state.run_id).exists()


def test_plan_figure_slots_removes_orphan_file_when_save_state_fails(tmp_path) -> None:
    store, state = _draft_ready_state(tmp_path)
    failing_store = FailingSaveStateStore(data_dir=store.data_dir)

    with pytest.raises(RuntimeError, match="save_state failure"):
        FigureSlotPlannerService(failing_store).plan_figure_slots(state.run_id)

    reloaded = store.load_state(state.run_id)
    assert reloaded.workflow_status == WorkflowStatus.DRAFT_V1_CREATED
    assert reloaded.figure_slots_ref is None
    assert reloaded.figure_slots_result_id is None
    assert not _figure_path(store, state.run_id).exists()
    assert not (_figure_path(store, state.run_id).with_suffix(".json.tmp")).exists()


def test_plan_figure_slots_rejects_stale_unrecorded_result_file(tmp_path) -> None:
    store, state = _draft_ready_state(tmp_path)
    stale_path = _figure_path(store, state.run_id)
    stale_payload = {"stale": True}
    stale_path.write_text(json.dumps(stale_payload, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ValueError, match="stale|未被 state 承认"):
        FigureSlotPlannerService(store).plan_figure_slots(state.run_id)

    reloaded = store.load_state(state.run_id)
    assert reloaded.workflow_status == WorkflowStatus.DRAFT_V1_CREATED
    assert reloaded.figure_slots_ref is None
    assert reloaded.figure_slots_result_id is None
    assert json.loads(stale_path.read_text(encoding="utf-8")) == stale_payload


def test_plan_figure_slots_human_confirmation_section_is_optional(tmp_path) -> None:
    store, state = _draft_ready_state(tmp_path)
    assert state.outline is not None
    section_id = state.section_plan[0].section_id
    state.section_plan[0].needs_human_confirmation = True
    state.outline.chapters[0]["sections"][0]["needs_human_confirmation"] = True
    store.save_state(state)

    result = FigureSlotPlannerService(store).plan_figure_slots(state.run_id)

    slot = next(item for item in result.figure_slots if item.section_id == section_id)
    assert slot.required is False
    assert slot.status == "missing"
    assert "该章节存在需人工确认内容" in slot.warnings[0]
    assert "不作为产品事实证据" in slot.reason


def test_plan_figure_slots_does_not_downgrade_system_overview_by_title_keyword(tmp_path) -> None:
    store, state = _draft_ready_state(tmp_path)
    _replace_first_section_metadata(
        store,
        state,
        section_title="系统概述",
        required_evidence_ids=["ev_product"],
        required_capability_ids=["cap_current"],
    )

    result = FigureSlotPlannerService(store).plan_figure_slots(state.run_id)

    slot = next(item for item in result.figure_slots if item.section_title == "系统概述")
    assert slot.required is True
    assert slot.status == "missing"
    assert "文档展示材料" in slot.reason
    assert "不作为产品事实证据" in slot.reason


def test_figure_slot_planner_does_not_use_screenshot_as_required_evidence(
    tmp_path: Path,
) -> None:
    store, state = _draft_ready_state(tmp_path)
    state.evidence_map.append(
        product_evidence(
            evidence_id="ev_screenshot",
            source_id="screen_source",
            evidence_type=EvidenceType.PRODUCT_SCREENSHOT,
            summary="产品截图已登记但未做视觉解析",
        )
    )
    assert state.frozen_doc_plan is not None
    state.frozen_doc_plan.screenshot_policy = {
        "screenshot_evidence_ids": ["ev_screenshot"],
        "visual_parse_status": "not_performed",
        "can_use_screenshot_as_strong_evidence": False,
        "can_use_screenshot_as_product_fact": False,
        "screenshot_usage": "figure_placeholder_only",
        "screenshot_binding_status": "not_performed",
    }
    store.save_state(state)
    draft_before = json.loads(_draft_path(store, state.run_id).read_text(encoding="utf-8"))

    result = FigureSlotPlannerService(store).plan_figure_slots(state.run_id)

    raw_result = result.model_dump(mode="json")
    raw_text = json.dumps(raw_result, ensure_ascii=False)
    assert "ev_screenshot" not in raw_text
    for slot in raw_result["figure_slots"]:
        assert "required_evidence_ids" not in slot
        assert "citations" not in slot
        assert "evidence_id" not in slot
        assert "screenshot_source_id" not in slot
    assert "screenshot_file_path" not in raw_text
    assert "screenshot_source_id" not in raw_text
    assert all(slot.status == "missing" for slot in result.figure_slots)
    assert result.safety_report.does_not_bind_real_screenshots is True
    assert result.safety_report.does_not_use_ocr is True
    assert result.safety_report.does_not_use_vision_model is True
    assert json.loads(_draft_path(store, state.run_id).read_text(encoding="utf-8")) == draft_before


def test_plan_figure_slots_only_grounded_content_generates_slot(tmp_path) -> None:
    store, state = _draft_ready_state(tmp_path)
    _clear_all_grounded_content(store, state)

    result = FigureSlotPlannerService(store).plan_figure_slots(state.run_id)

    assert result.figure_slots == []
    assert result.summary.total_slots == 0
    assert result.summary.required_slots == 0
    assert result.summary.optional_slots == 0
    assert result.summary.missing_slots == 0


def test_figure_slot_result_rejects_real_screenshot_binding_fields() -> None:
    payload = {
        "result_id": "fig_slots_test_v1",
        "draft_version": "v1",
        "source_draft_ref": "drafts/draft_v1.json",
        "created_at": "2026-06-08T00:00:00+00:00",
        "figure_slots": [
            {
                "slot_id": "fig_slot_001",
                "section_id": "sec_001",
                "section_path": ["核心功能说明", "数据集管理"],
                "section_title": "数据集管理",
                "recommended_caption": "图 1-1 数据集管理页面",
                "recommended_screenshot": "数据集管理页面截图",
                "reason": "建议补充对应页面截图。",
                "required": True,
                "status": "missing",
                "user_action": "请补充【数据集管理】相关页面截图",
                "warnings": [],
                "screenshot_file_path": "sources/screenshots/a.png",
            }
        ],
        "summary": {
            "total_slots": 1,
            "required_slots": 1,
            "optional_slots": 0,
            "missing_slots": 1,
        },
        "safety_report": {
            "body_unchanged": True,
            "does_not_claim_existing_images": True,
            "does_not_modify_citations": True,
            "does_not_modify_evidence_ids_used": True,
            "does_not_modify_draft_content": True,
            "does_not_bind_real_screenshots": True,
            "does_not_use_ocr": True,
            "does_not_use_vision_model": True,
            "warnings": [],
        },
    }

    with pytest.raises(ValidationError, match="screenshot_file_path"):
        FigureSlotResult.model_validate(payload)


def test_figure_slot_validator_rejects_bad_summary(tmp_path) -> None:
    store, state = _draft_ready_state(tmp_path)
    result = FigureSlotPlannerService(store).plan_figure_slots(state.run_id)
    result.summary.required_slots += 1

    with pytest.raises(ValueError, match="summary"):
        FigureSlotValidator().validate(result, state.section_plan, state)

    reloaded = store.load_state(state.run_id)
    assert len(reloaded.draft_versions) == 1
    assert reloaded.draft_versions[0].version_label == DraftVersionLabel.V1
