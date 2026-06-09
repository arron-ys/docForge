"""Checklist-only quality gate before draft writing."""

from __future__ import annotations

from typing import Any

from docforge_core.agents._shared import transition, unique_strings
from docforge_core.agents.outline_traversal import iter_outline_sections
from docforge_core.agents.outline_validator import OutlineValidator
from docforge_core.agents.section_evidence_policy import assess_section_evidence
from docforge_core.agents.section_plan_validator import SectionPlanValidator
from docforge_core.agents.title_safety import is_forbidden_title
from docforge_core.agents.writing_plan_safety_items import (
    collect_writing_plan_safety_items_from_outline,
    collect_writing_plan_safety_items_from_section_plan,
)
from docforge_core.agents.writing_plan_safety_verifier import (
    FAIL_CLOSED_REASON,
    MISSING_LLM_PROVIDER_REASON,
    WritingPlanSafetyVerifier,
    WritingPlanSafetyVerifierProtocol,
)
from docforge_core.domain.enums import GateType, LockedStatus, NextAction, WorkflowStatus
from docforge_core.domain.schemas import (
    DocForgeState,
    FrozenDocPlan,
    QualityGateReport,
)
from docforge_core.io.state_store import StateStore
from docforge_core.llm.base import LLMProvider


class PlanQualityGate:
    """Run a deterministic checklist without scoring or writing content."""

    def __init__(
        self,
        state_store: StateStore | None = None,
        writing_plan_safety_verifier: WritingPlanSafetyVerifierProtocol | None = None,
        llm_provider: LLMProvider | None = None,
    ) -> None:
        self.state_store = state_store or StateStore()
        self.outline_validator = OutlineValidator()
        self.section_plan_validator = SectionPlanValidator()
        self.writing_plan_safety_verifier = (
            writing_plan_safety_verifier
            or WritingPlanSafetyVerifier(llm_provider=llm_provider)
        )

    def run(self, run_id: str) -> DocForgeState:
        state = self.state_store.load_state(run_id)
        if state.workflow_status != WorkflowStatus.OUTLINE_CREATED:
            raise ValueError("PlanQualityGate 要求 workflow_status 为 OUTLINE_CREATED")
        plan = state.frozen_doc_plan
        if plan is None:
            raise ValueError("PlanQualityGate 要求存在 frozen_doc_plan")
        if state.outline is None:
            raise ValueError("PlanQualityGate 要求存在 outline")
        if not state.section_plan:
            raise ValueError("PlanQualityGate 要求存在 section_plan")

        checklist: list[dict[str, Any]] = []
        blockers: list[str] = []
        majors: list[str] = []
        minors: list[str] = []
        missing: list[str] = []

        def check(name: str, passed: bool, severity: str, issue: str = "") -> None:
            checklist.append(
                {"name": name, "passed": passed, "severity": severity, "issue": issue}
            )
            if passed or not issue:
                return
            if severity == "blocker":
                blockers.append(issue)
            elif severity == "major":
                majors.append(issue)
            else:
                minors.append(issue)

        software_identity = plan.software_identity
        product_name = str(software_identity.get("target_product_name", "")).strip()
        check("软件名称是否明确", bool(product_name), "major", "软件名称缺失")
        if not product_name:
            missing.append("请补充软件名称。")

        version = self._software_version(state, plan)
        check("软件版本是否明确", bool(version), "major", "软件版本缺失")
        if not version:
            missing.append("请补充软件版本号。")

        primary_type = str(plan.diagnosis_snapshot.get("primary_type", "")).strip()
        check(
            "软件类型是否已确认",
            bool(primary_type and primary_type != "待确认"),
            "major",
            "软件类型待确认",
        )
        check(
            "文档模板是否已冻结",
            plan.locked_status == LockedStatus.LOCKED
            and bool(plan.template_decision.get("base_template_id")),
            "blocker",
            "FrozenDocPlan 或模板未锁定",
        )

        locked_titles = plan.chapter_policy.get("locked_top_level_chapters", [])
        outline_titles = [item.get("title") for item in state.outline.chapters]
        check(
            "一级目录是否已冻结",
            bool(locked_titles) and outline_titles == locked_titles,
            "blocker",
            "outline 一级目录违反 FrozenDocPlan",
        )

        factual_filter = plan.evidence_policy.get("factual_evidence_filter", {})
        style_filter = plan.evidence_policy.get("style_reference_filter", {})
        check(
            "是否区分参考资料和自有产品资料",
            factual_filter == {
                "corpus_type": "product_evidence",
                "allowed_usage": "factual_evidence",
            }
            and style_filter
            == {"corpus_type": "reference_style", "allowed_usage": "style_only"},
            "blocker",
            "证据隔离 filter 不正确",
        )

        current_capabilities = plan.feature_policy.get("current_capabilities", [])
        trace = plan.evidence_policy.get("evidence_trace", [])
        product_ids = set(
            plan.evidence_policy.get("allowed_product_evidence_ids", [])
        )
        traced_capability_ids = {
            item.get("capability_id")
            for item in trace
            if item.get("evidence_id") in product_ids
            and item.get("corpus_type") == "product_evidence"
            and item.get("allowed_usage") == "factual_evidence"
        }
        current_has_evidence = all(
            self._valid_capability_supports(item.get("evidence_supports"), product_ids)
            and item.get("capability_id") in traced_capability_ids
            for item in current_capabilities
        ) and all(
            item.get("corpus_type") == "product_evidence"
            and item.get("allowed_usage") == "factual_evidence"
            and item.get("evidence_id") in product_ids
            for item in trace
        )
        check(
            "当前功能是否均有 product_evidence",
            bool(current_capabilities) and current_has_evidence,
            "blocker",
            "当前功能缺少 product_evidence",
        )

        outline_evidence = self._outline_evidence_ids(state)
        section_evidence = {
            evidence_id
            for item in state.section_plan
            for evidence_id in item.required_evidence_ids
        }
        reference_ids = set(
            plan.evidence_policy.get("allowed_reference_style_ids", [])
        )
        check(
            "参考资料是否未被当作事实使用",
            not (outline_evidence | section_evidence).intersection(reference_ids),
            "blocker",
            "outline 或 section_plan 使用了 reference_style evidence",
        )
        check(
            "SectionPlan 是否只绑定允许的 product_evidence",
            section_evidence.issubset(product_ids),
            "blocker",
            "section_plan 使用了未知或非 product evidence",
        )

        forbidden = plan.feature_policy.get("forbidden_as_current_feature_names", [])
        outline_nodes = iter_outline_sections(state.outline)
        outline_sections = [
            (node.chapter_title, node.section) for node in outline_nodes
        ]
        section_titles = [
            str(section.get("title", "")) for _, section in outline_sections
        ] + [item.section_title for item in state.section_plan]
        check(
            "是否存在 planned / unknown 功能被写成当前功能",
            not any(is_forbidden_title(title, forbidden) for title in section_titles),
            "blocker",
            "planned / unknown / unsupported 功能进入当前章节",
        )

        needs_confirmation = [
            f"{chapter_title} / {section.get('title')}"
            for chapter_title, section in outline_sections
            if section.get("needs_human_confirmation")
        ]
        capability_without_evidence: list[str] = []
        capability_mismatches: list[str] = []
        fact_mismatches: list[str] = []
        for chapter_title, section in outline_sections:
            location = f"{chapter_title} / {section.get('title')}"
            evidence_ids = set(section.get("required_evidence_ids", []))
            assessment = assess_section_evidence(section, plan)
            if assessment.is_capability_related and not evidence_ids:
                capability_without_evidence.append(location)
            if (
                assessment.capability_evidence_ids
                and not assessment.capability_evidence_ids.issubset(evidence_ids)
            ) or assessment.unresolved_capability_ids or assessment.unresolved_title_match:
                capability_mismatches.append(location)
            if (
                assessment.fact_evidence_ids
                and not assessment.fact_evidence_ids.issubset(evidence_ids)
            ) or assessment.unresolved_fact_ids:
                fact_mismatches.append(location)
        for item in unique_strings([*needs_confirmation, *capability_without_evidence]):
            missing.append(f"请补充“{item}”所需的产品证据。")
        check(
            "所有能力相关章节是否绑定 product_evidence",
            not capability_without_evidence,
            "blocker",
            "能力相关章节缺少 product_evidence",
        )
        check(
            "能力章节 evidence 是否与 capability 匹配",
            not capability_mismatches,
            "blocker",
            "能力章节 evidence 与 capability 不匹配",
        )
        check(
            "能力章节 evidence 是否与 fact 匹配",
            not fact_mismatches,
            "blocker",
            "能力章节 evidence 与 fact 不匹配",
        )
        check(
            "是否存在必须向用户反问的缺失信息",
            not needs_confirmation and not capability_without_evidence,
            "major",
            "部分章节需要补充产品证据",
        )

        try:
            self.outline_validator.validate_outline(state.outline, plan)
        except ValueError as exc:
            check("Outline 是否违反 FrozenDocPlan", False, "blocker", str(exc))
        else:
            check("Outline 是否违反 FrozenDocPlan", True, "blocker")

        expected_sections = {
            (
                node.chapter_title,
                str(node.section.get("title", "")),
                str(node.section.get("section_id", "")),
                node.section_level,
                tuple(node.section_path),
                node.parent_section_title,
            ): tuple(node.section.get("required_evidence_ids", []))
            for node in outline_nodes
        }
        planned_sections = {
            (
                item.chapter_title,
                item.section_title,
                item.section_id,
                item.section_level,
                tuple(item.section_path),
                item.parent_section_title,
            ): tuple(item.required_evidence_ids)
            for item in state.section_plan
            if item.chapter_title and item.section_title and item.writing_goal
        }
        check(
            "SectionPlan 是否完整",
            expected_sections == planned_sections
            and len(state.section_plan) == len(expected_sections),
            "major",
            "section_plan 不完整",
        )
        try:
            self.section_plan_validator.validate_section_plan_matches_outline(
                state.outline,
                state.section_plan,
            )
        except ValueError:
            check(
                "SectionPlan 是否与 Outline 完全一致",
                False,
                "blocker",
                "section_plan 与 outline 不一致",
            )
        else:
            check("SectionPlan 是否与 Outline 完全一致", True, "blocker")
        if any(len(item.writing_goal.strip()) < 6 for item in state.section_plan):
            minors.append("个别章节 writing_goal 过短")

        safety_items = [
            *collect_writing_plan_safety_items_from_outline(state.outline),
            *collect_writing_plan_safety_items_from_section_plan(state.section_plan),
        ]
        for item_index, safety_item in enumerate(safety_items):
            safety_item["item_index"] = item_index
        try:
            safety_results = self.writing_plan_safety_verifier.verify_items(safety_items)
        except Exception:
            check(
                "写作计划字段语义安全校验",
                False,
                "blocker",
                "写作计划语义安全校验失败",
            )
        else:
            unsafe_safety_results = [
                item for item in safety_results if item.get("safe") is not True
            ]
            inconsistent_safe_results = [
                item
                for item in safety_results
                if item.get("safe") is True and item.get("risk_type", "none") != "none"
            ]
            failed_closed = (
                len(safety_results) != len(safety_items)
                or bool(inconsistent_safe_results)
                or any(
                    item.get("reason") in {
                        FAIL_CLOSED_REASON,
                        MISSING_LLM_PROVIDER_REASON,
                    }
                    for item in unsafe_safety_results
                )
            )
            if failed_closed:
                check(
                    "写作计划字段语义安全校验",
                    False,
                    "blocker",
                    "写作计划语义安全校验失败",
                )
            else:
                check(
                    "写作计划字段语义安全校验",
                    not unsafe_safety_results,
                    "blocker",
                    "写作计划字段包含不安全写作指令",
                )

        passed = not blockers and not majors and not missing
        next_action = NextAction.WRITE_DRAFT if passed else NextAction.ASK_MISSING_INFORMATION
        state.plan_quality_gate_report = QualityGateReport(
            gate_type=GateType.PLAN_QUALITY_GATE,
            target_id=state.outline.outline_id,
            passed=passed,
            checklist_results=checklist,
            blocker_issues=unique_strings(blockers),
            major_issues=unique_strings(majors),
            minor_issues=unique_strings(minors),
            missing_information=unique_strings(missing),
            required_user_questions=unique_strings(missing),
            summary="PlanQualityGate 通过" if passed else "PlanQualityGate 未通过",
            next_action=next_action,
        )
        state.plan_quality_gate_passed = passed
        for question in unique_strings(missing):
            if question not in state.pending_human_questions:
                state.pending_human_questions.append(question)
        transition(
            state,
            WorkflowStatus.OUTLINE_CREATED,
            WorkflowStatus.PLAN_GATE_PASSED if passed else WorkflowStatus.PLAN_GATE_FAILED,
            next_action,
            "PlanQualityGate.run",
            "plan quality gate passed" if passed else "plan quality gate failed",
        )
        self.state_store.save_state(state)
        return state

    @staticmethod
    def _software_version(state: DocForgeState, plan: FrozenDocPlan) -> str:
        return str(
            plan.software_identity.get("version")
            or plan.software_identity.get("software_version")
            or state.output_requirements.get("version")
            or state.output_requirements.get("software_version")
            or ""
        ).strip()

    @staticmethod
    def _outline_evidence_ids(state: DocForgeState) -> set[str]:
        if state.outline is None:
            return set()
        return {
            evidence_id
            for node in iter_outline_sections(state.outline)
            for evidence_id in node.section.get("required_evidence_ids", [])
        }

    @staticmethod
    def _valid_capability_supports(supports: Any, product_ids: set[str]) -> bool:
        if not isinstance(supports, list) or not supports:
            return False
        evidence_ids = {
            support.get("evidence_id")
            for support in supports
            if isinstance(support, dict) and support.get("evidence_id")
        }
        return len(evidence_ids) == len(supports) and evidence_ids.issubset(product_ids)
