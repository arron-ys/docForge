"""Plan missing figure slots after draft_v1 without binding real screenshots."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from docforge_core.domain.enums import NextAction, WorkflowStatus
from docforge_core.domain.schemas import (
    DocForgeState,
    FigureSlotItem,
    FigureSlotResult,
    FigureSlotSafetyReport,
    FigureSlotSummary,
    FrozenDocPlan,
    SectionPlan,
)
from docforge_core.io.run_paths import get_drafts_dir, get_state_file
from docforge_core.io.state_store import StateStore

from ._shared import transition
from .section_plan_validator import SectionPlanValidator

FORBIDDEN_SLOT_KEYS = {
    "screenshot_file_path",
    "screenshot_source_id",
    "image_path",
    "asset_id",
    "evidence_id",
    "existing_screenshot",
    "uploaded_screenshot",
    "matched_screenshot",
    "bound_screenshot",
}

FORBIDDEN_STATUS_VALUES = {"existing", "bound", "matched", "uploaded", "attached"}


class FigureSlotValidator:
    """Validate Sprint 10 figure-slot output boundaries."""

    def validate(
        self,
        result: FigureSlotResult,
        section_plan: list[SectionPlan],
        state: DocForgeState,
    ) -> None:
        if result.source_draft_ref != "drafts/draft_v1.json":
            raise ValueError("FigureSlotResult source_draft_ref 必须为 drafts/draft_v1.json")
        if result.draft_version != "v1":
            raise ValueError("FigureSlotResult draft_version 必须为 v1")
        if any(item.content_ref == "drafts/figure_slots_v1.json" for item in state.draft_versions):
            raise ValueError("draft_versions 只能保存正文版本，不得保存 FigureSlotResult")

        plan_by_id = {item.section_id: item for item in section_plan}
        slot_ids: set[str] = set()
        section_slot_count: dict[str, int] = {}
        raw = result.model_dump(mode="json")
        self._reject_forbidden_binding_fields(raw)

        for slot in result.figure_slots:
            if slot.slot_id in slot_ids:
                raise ValueError(f"slot_id 重复: {slot.slot_id}")
            slot_ids.add(slot.slot_id)
            section_slot_count[slot.section_id] = section_slot_count.get(slot.section_id, 0) + 1
            if section_slot_count[slot.section_id] > 1:
                raise ValueError(f"每个 section 最多只能生成 1 个 figure slot: {slot.section_id}")

            plan = plan_by_id.get(slot.section_id)
            if plan is None:
                raise ValueError(f"figure slot section_id 不存在于 SectionPlan: {slot.section_id}")
            if slot.section_path != plan.section_path:
                raise ValueError(f"figure slot section_path 与 SectionPlan 不一致: {slot.section_id}")
            if slot.section_title != plan.section_title:
                raise ValueError(f"figure slot section_title 与 SectionPlan 不一致: {slot.section_id}")
            if not slot.recommended_caption.strip():
                raise ValueError("recommended_caption 不得为空")
            if not slot.recommended_screenshot.strip():
                raise ValueError("recommended_screenshot 不得为空")
            if not slot.reason.strip():
                raise ValueError("reason 不得为空")
            if not slot.user_action.strip():
                raise ValueError("user_action 不得为空")
            if slot.status != "missing":
                raise ValueError("FigureSlot status 本 Sprint 只能是 missing")
            if not isinstance(slot.required, bool):
                raise ValueError("required 必须是 bool")
            if not isinstance(slot.warnings, list):
                raise ValueError("warnings 必须是 list")

        self._validate_summary(result)
        self._validate_safety_report(result.safety_report)

    @staticmethod
    def _validate_summary(result: FigureSlotResult) -> None:
        total = len(result.figure_slots)
        required = sum(1 for slot in result.figure_slots if slot.required)
        optional = total - required
        missing = sum(1 for slot in result.figure_slots if slot.status == "missing")
        expected = FigureSlotSummary(
            total_slots=total,
            required_slots=required,
            optional_slots=optional,
            missing_slots=missing,
        )
        if result.summary != expected:
            raise ValueError("FigureSlot summary 统计不准确")

    @staticmethod
    def _validate_safety_report(report: FigureSlotSafetyReport) -> None:
        checks = {
            "body_unchanged": report.body_unchanged,
            "does_not_claim_existing_images": report.does_not_claim_existing_images,
            "does_not_modify_citations": report.does_not_modify_citations,
            "does_not_modify_evidence_ids_used": report.does_not_modify_evidence_ids_used,
            "does_not_modify_draft_content": report.does_not_modify_draft_content,
            "does_not_bind_real_screenshots": report.does_not_bind_real_screenshots,
            "does_not_use_ocr": report.does_not_use_ocr,
            "does_not_use_vision_model": report.does_not_use_vision_model,
        }
        failed = [name for name, ok in checks.items() if ok is not True]
        if failed:
            raise ValueError("FigureSlot safety_report 未通过: " + ", ".join(failed))

    @classmethod
    def _reject_forbidden_binding_fields(cls, value: Any) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if key in FORBIDDEN_SLOT_KEYS:
                    raise ValueError(f"FigureSlotResult 不允许真实截图绑定字段: {key}")
                if key == "status" and child in FORBIDDEN_STATUS_VALUES:
                    raise ValueError(f"FigureSlotResult 不允许已绑定截图状态: {child}")
                cls._reject_forbidden_binding_fields(child)
        elif isinstance(value, list):
            for child in value:
                cls._reject_forbidden_binding_fields(child)


class FigureSlotPlannerService:
    """Create drafts/figure_slots_v1.json from draft_v1 and SectionPlan."""

    def __init__(
        self,
        state_store: StateStore | None = None,
        validator: FigureSlotValidator | None = None,
    ) -> None:
        self.state_store = state_store or StateStore()
        self.validator = validator or FigureSlotValidator()
        self.section_plan_validator = SectionPlanValidator()

    def plan_figure_slots(self, run_id: str) -> FigureSlotResult:
        state = self.state_store.load_state(run_id)
        plan = self._require_ready_state(state)
        assert state.outline is not None
        self.section_plan_validator.validate_section_plan_matches_outline(
            state.outline,
            state.section_plan,
        )

        drafts_dir = get_drafts_dir(state.run_id, self.state_store.data_dir)
        draft_path = drafts_dir / "draft_v1.json"
        tmp_path = drafts_dir / "figure_slots_v1.json.tmp"
        figure_path = drafts_dir / "figure_slots_v1.json"
        state_path = get_state_file(state.run_id, self.state_store.data_dir)
        original_state_bytes = state_path.read_bytes()
        if tmp_path.exists():
            tmp_path.unlink()
        if not draft_path.exists():
            raise FileNotFoundError(f"draft_v1.json 不存在: {draft_path}")
        if figure_path.exists():
            if state.figure_slots_ref is None:
                raise ValueError("存在未被 state 承认的 stale figure_slots_v1.json")
            raise ValueError("DRAFT_V1_CREATED 状态下不应已存在 figure_slots_v1.json")

        before_hash = self._sha256(draft_path)
        draft_document = json.loads(draft_path.read_text(encoding="utf-8"))
        self._validate_draft_matches_plan(draft_document, state)

        result = self._build_result(state, plan, draft_document)
        self.validator.validate(result, state.section_plan, state)

        try:
            if self._sha256(draft_path) != before_hash:
                raise ValueError("draft_v1.json 在 FigureSlotPlanner 执行期间发生变化")
            tmp_path.write_text(
                json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            tmp_path.replace(figure_path)
            if self._sha256(draft_path) != before_hash:
                if figure_path.exists():
                    figure_path.unlink()
                raise ValueError("draft_v1.json 在 FigureSlotResult 写入后发生变化")

            state.figure_slots_ref = "drafts/figure_slots_v1.json"
            state.figure_slots_result_id = result.result_id
            transition(
                state,
                WorkflowStatus.DRAFT_V1_CREATED,
                WorkflowStatus.FIGURE_SLOTS_PLANNED,
                NextAction.AUDIT_DRAFT,
                "FigureSlotPlannerService.plan_figure_slots",
                "figure slots planned from draft_v1 without binding screenshots",
            )
            self.state_store.save_state(state)
            saved_state = self.state_store.load_state(state.run_id)
            self._validate_success_state(saved_state, result, figure_path)
        except Exception:
            if tmp_path.exists():
                tmp_path.unlink()
            if figure_path.exists():
                figure_path.unlink()
            self._restore_state_file(state_path, original_state_bytes)
            raise
        return result

    @staticmethod
    def _require_ready_state(state: DocForgeState) -> FrozenDocPlan:
        if state.workflow_status != WorkflowStatus.DRAFT_V1_CREATED:
            raise ValueError("FigureSlotPlanner 要求 workflow_status 为 DRAFT_V1_CREATED")
        if state.next_action != NextAction.PLAN_FIGURE_SLOTS:
            raise ValueError("FigureSlotPlanner 要求 next_action 为 PLAN_FIGURE_SLOTS")
        if state.frozen_doc_plan is None:
            raise ValueError("FigureSlotPlanner 要求存在 FrozenDocPlan")
        if not state.section_plan:
            raise ValueError("FigureSlotPlanner 要求存在 SectionPlan")
        if state.outline is None:
            raise ValueError("FigureSlotPlanner 要求存在 DocumentOutline")
        if not any(item.version_label.value == "v1" for item in state.draft_versions):
            raise ValueError("FigureSlotPlanner 要求 state.draft_versions 中存在 v1 正文版本")
        return state.frozen_doc_plan

    @staticmethod
    def _sha256(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    @staticmethod
    def _restore_state_file(state_path: Path, original_state_bytes: bytes) -> None:
        rollback_path = state_path.with_suffix(".json.figure_slot_rollback.tmp")
        try:
            rollback_path.write_bytes(original_state_bytes)
            rollback_path.replace(state_path)
        finally:
            if rollback_path.exists():
                rollback_path.unlink()

    @staticmethod
    def _validate_success_state(
        state: DocForgeState,
        result: FigureSlotResult,
        figure_path: Path,
    ) -> None:
        if not figure_path.exists():
            raise ValueError("FigureSlotPlanner 成功状态缺少 figure_slots_v1.json")
        if state.figure_slots_ref != "drafts/figure_slots_v1.json":
            raise ValueError("FigureSlotPlanner 成功状态 figure_slots_ref 不正确")
        if state.figure_slots_result_id != result.result_id:
            raise ValueError("FigureSlotPlanner 成功状态 figure_slots_result_id 不正确")
        if state.workflow_status != WorkflowStatus.FIGURE_SLOTS_PLANNED:
            raise ValueError("FigureSlotPlanner 成功状态 workflow_status 不正确")
        if state.next_action != NextAction.AUDIT_DRAFT:
            raise ValueError("FigureSlotPlanner 成功状态 next_action 不正确")

    @staticmethod
    def _validate_draft_matches_plan(draft_document: dict[str, Any], state: DocForgeState) -> None:
        if draft_document.get("version_label") != "v1":
            raise ValueError("draft_v1.json version_label 必须为 v1")
        if not isinstance(draft_document.get("chapters"), list):
            raise ValueError("draft_v1.json 缺少 chapters")
        draft_sections = FigureSlotPlannerService._draft_sections_by_id(draft_document)
        expected_ids = {item.section_id for item in state.section_plan}
        if set(draft_sections) != expected_ids:
            raise ValueError("draft_v1.json sections 与 SectionPlan 不一致")
        for plan in state.section_plan:
            draft_section = draft_sections[plan.section_id]
            if draft_section.get("section_title") != plan.section_title:
                raise ValueError("draft_v1.json section_title 与 SectionPlan 不一致")
            if draft_section.get("section_path") != plan.section_path:
                raise ValueError("draft_v1.json section_path 与 SectionPlan 不一致")

    @staticmethod
    def _draft_sections_by_id(draft_document: dict[str, Any]) -> dict[str, dict[str, Any]]:
        sections: dict[str, dict[str, Any]] = {}
        for chapter in draft_document.get("chapters", []):
            if not isinstance(chapter, dict):
                continue
            raw_sections = chapter.get("sections", [])
            if not isinstance(raw_sections, list):
                continue
            for section in raw_sections:
                if isinstance(section, dict):
                    section_id = str(section.get("section_id", ""))
                    if section_id:
                        sections[section_id] = section
        return sections

    def _build_result(
        self,
        state: DocForgeState,
        _plan: FrozenDocPlan,
        draft_document: dict[str, Any],
    ) -> FigureSlotResult:
        draft_sections = self._draft_sections_by_id(draft_document)
        slots: list[FigureSlotItem] = []
        for section in state.section_plan:
            slot = self._slot_for_section(section, len(slots) + 1, draft_sections.get(section.section_id))
            if slot is not None:
                slots.append(slot)
        summary = FigureSlotSummary(
            total_slots=len(slots),
            required_slots=sum(1 for slot in slots if slot.required),
            optional_slots=sum(1 for slot in slots if not slot.required),
            missing_slots=len(slots),
        )
        return FigureSlotResult(
            result_id=f"fig_slots_{state.run_id}_v1",
            draft_version="v1",
            source_draft_ref="drafts/draft_v1.json",
            created_at=datetime.now(UTC).isoformat(),
            figure_slots=slots,
            summary=summary,
            safety_report=FigureSlotSafetyReport(),
        )

    def _slot_for_section(
        self,
        section: SectionPlan,
        slot_index: int,
        draft_section: dict[str, Any] | None,
    ) -> FigureSlotItem | None:
        has_grounded_content = bool(
            section.required_capability_ids
            or section.required_fact_ids
            or section.required_evidence_ids
        )
        if not has_grounded_content:
            return None

        required = not section.needs_human_confirmation
        warnings: list[str] = []
        if section.needs_human_confirmation:
            warnings.append("该章节存在需人工确认内容，建议先补充产品事实证据，再补充截图。")

        caption = self._caption(section)
        reason = (
            "该章节已有结构化证据/能力/事实绑定，建议补充对应页面截图，截图只作为文档展示材料，不作为产品事实证据。"
            if required
            else "该章节仍需人工确认，本图位仅作为可选补图建议，不作为产品事实证据。"
        )

        section_title = str(
            (draft_section or {}).get("section_title") or section.section_title
        )
        return FigureSlotItem(
            slot_id=f"fig_slot_{slot_index:03d}",
            section_id=section.section_id,
            section_path=section.section_path,
            section_title=section_title,
            recommended_caption=caption,
            recommended_screenshot=f"{section.section_title}页面截图",
            reason=reason,
            required=required,
            status="missing",
            user_action=f"请补充【{section.section_title}】相关页面截图",
            warnings=warnings,
        )

    @staticmethod
    def _caption(section: SectionPlan) -> str:
        chapter_number = FigureSlotPlannerService._first_number(section.section_id)
        return f"图 {chapter_number}-1 {section.section_title}页面"

    @staticmethod
    def _first_number(value: str) -> int:
        digits = ""
        for char in value:
            if char.isdigit():
                digits += char
            elif digits:
                break
        if not digits:
            return 1
        return max(1, int(digits))
