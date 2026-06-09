"""Generate the first structured draft from a passed SectionPlan."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from docforge_core.domain.enums import (
    AllowedUsage,
    CorpusType,
    DraftVersionLabel,
    EvidenceType,
    GateType,
    LockedStatus,
    NextAction,
    WorkflowStatus,
)
from docforge_core.domain.schemas import (
    DocForgeState,
    DraftVersion,
    EvidenceItem,
    FrozenDocPlan,
    QualityGateReport,
    SectionPlan,
)
from docforge_core.io.run_paths import get_drafts_dir
from docforge_core.io.state_store import StateStore
from docforge_core.llm.base import LLMMessage, LLMProvider
from docforge_core.llm.prompt_loader import load_prompt

from ._shared import transition
from .outline_traversal import iter_outline_sections
from .outline_validator import OutlineValidator
from .section_draft_safety_verifier import SectionDraftSafetyVerifier
from .section_draft_validator import SectionDraftValidator
from .section_plan_validator import SectionPlanValidator


class WriterAgent:
    """Create draft_v1.json without changing the frozen plan or section plan."""

    def __init__(
        self,
        state_store: StateStore | None = None,
        llm_provider: LLMProvider | None = None,
    ) -> None:
        self.state_store = state_store or StateStore()
        self.llm_provider = llm_provider
        self.validator = SectionDraftValidator()
        self.outline_validator = OutlineValidator()
        self.section_plan_validator = SectionPlanValidator()
        self.section_draft_safety_verifier = SectionDraftSafetyVerifier(llm_provider)

    def write_v1_draft(self, run_id: str) -> DocForgeState:
        state = self.state_store.load_state(run_id)
        plan = self._require_ready_state(state)
        assert state.outline is not None
        self.outline_validator.validate_outline(state.outline, plan)
        self._validate_section_plan_ready_for_writer(state)

        if self.llm_provider is None:
            raise ValueError("WriterAgent 要求 llm_provider")
        if any(item.version_label == DraftVersionLabel.V1 for item in state.draft_versions):
            raise ValueError("v1 草稿已存在，不允许重复生成")

        drafts_dir = get_drafts_dir(state.run_id, self.state_store.data_dir)
        draft_path = drafts_dir / "draft_v1.json"
        if draft_path.exists():
            raise ValueError("draft_v1.json 已存在，不允许覆盖")

        draft_id = f"draft_{state.run_id}_v1"
        section_plan_by_id = {item.section_id: item for item in state.section_plan}
        warnings: list[str] = []
        draft_sections_by_id: dict[str, dict[str, Any]] = {}

        for node in iter_outline_sections(state.outline):
            section_id = str(node.section.get("section_id", ""))
            section_plan = section_plan_by_id.get(section_id)
            if section_plan is None:
                raise ValueError(f"section_plan 缺少 outline section: {section_id}")
            evidence_bundle = self._build_section_evidence_bundle(
                state,
                section_plan,
                plan,
                warnings,
            )
            section_draft = self._generate_section_draft(
                plan,
                section_plan,
                evidence_bundle,
            )
            self.validator.validate_section_draft(
                section_draft,
                section_plan,
                evidence_bundle,
                plan,
            )
            self.section_draft_safety_verifier.verify(
                section_draft,
                self._safe_section_plan_payload(section_plan),
                evidence_bundle,
                self._safe_writing_style_payload(plan),
            )
            draft_sections_by_id[section_id] = self._project_section_draft(
                section_draft,
                section_plan,
            )

        chapters = self._build_draft_chapters(state, draft_sections_by_id)
        draft_document = {
            "draft_id": draft_id,
            "version_label": DraftVersionLabel.V1.value,
            "based_on_plan_id": plan.plan_id,
            "based_on_outline_id": state.outline.outline_id,
            "created_at": datetime.now(UTC).isoformat(),
            "chapters": chapters,
            "warnings": warnings,
        }

        drafts_dir.mkdir(parents=True, exist_ok=True)
        tmp_path = drafts_dir / "draft_v1.json.tmp"
        try:
            tmp_path.write_text(
                json.dumps(draft_document, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            tmp_path.replace(draft_path)
        except Exception:
            if tmp_path.exists():
                tmp_path.unlink()
            raise

        draft_version = DraftVersion(
            draft_id=draft_id,
            version_label=DraftVersionLabel.V1,
            based_on_plan_id=plan.plan_id,
            based_on_outline_id=state.outline.outline_id,
            content_ref="drafts/draft_v1.json",
            revision_notes="v1 draft generated from section plan",
        )
        state.draft_versions.append(draft_version)
        state.current_draft_id = draft_version.draft_id
        state.current_draft_version = draft_version.version_label.value
        transition(
            state,
            WorkflowStatus.PLAN_GATE_PASSED,
            WorkflowStatus.DRAFT_V1_CREATED,
            NextAction.PLAN_FIGURE_SLOTS,
            "WriterAgent.write_v1_draft",
            "v1 draft generated from section plan",
        )
        self.state_store.save_state(state)
        return state

    @staticmethod
    def _require_ready_state(state: DocForgeState) -> FrozenDocPlan:
        if state.workflow_status != WorkflowStatus.PLAN_GATE_PASSED:
            raise ValueError("WriterAgent 要求 workflow_status 为 PLAN_GATE_PASSED")
        if state.next_action != NextAction.WRITE_DRAFT:
            raise ValueError("WriterAgent 要求 next_action 为 WRITE_DRAFT")
        if state.plan_quality_gate_passed is not True:
            raise ValueError("plan_quality_gate_passed 标记未通过")
        if state.outline is None:
            raise ValueError("WriterAgent 要求存在 outline")
        report = state.plan_quality_gate_report
        if not isinstance(report, QualityGateReport):
            raise ValueError("WriterAgent 要求 PlanQualityGate 已通过")
        if report.passed is not True:
            raise ValueError("WriterAgent 要求 PlanQualityGate 已通过")
        if report.gate_type != GateType.PLAN_QUALITY_GATE:
            raise ValueError("PlanQualityGate 报告类型不正确")
        if report.target_id != state.outline.outline_id:
            raise ValueError("PlanQualityGate target_id 不匹配")
        if report.next_action != NextAction.WRITE_DRAFT:
            raise ValueError("PlanQualityGate next_action 不正确")
        plan = state.frozen_doc_plan
        if plan is None:
            raise ValueError("WriterAgent 要求存在 frozen_doc_plan")
        if plan.locked_status != LockedStatus.LOCKED:
            raise ValueError("WriterAgent 要求 FrozenDocPlan 已锁定")
        if not state.section_plan:
            raise ValueError("WriterAgent 要求存在 section_plan")
        return plan

    def _validate_section_plan_ready_for_writer(self, state: DocForgeState) -> None:
        assert state.outline is not None
        self.section_plan_validator.validate_section_plan_matches_outline(
            state.outline,
            state.section_plan,
        )
        self._reject_required_screenshot_ids(state.section_plan)
        self._validate_outline_section_plan_order(state)

    @staticmethod
    def _reject_required_screenshot_ids(section_plan: list[SectionPlan]) -> None:
        for item in section_plan:
            if item.required_screenshot_ids:
                raise ValueError(
                    "Sprint 9 WriterAgent 不接受 required_screenshot_ids，"
                    "截图自动绑定已后置到 Phase 2；MVP 阶段由 FigureSlotPlanner 生成补图清单"
                )

    @staticmethod
    def _validate_outline_section_plan_order(state: DocForgeState) -> None:
        assert state.outline is not None
        outline_section_ids = [
            str(node.section.get("section_id", "")) for node in iter_outline_sections(state.outline)
        ]
        section_plan_ids = [item.section_id for item in state.section_plan]
        if outline_section_ids != section_plan_ids:
            raise ValueError("WriterAgent 要求 outline 与 section_plan 完全同步")

    def _build_section_evidence_bundle(
        self,
        state: DocForgeState,
        section_plan: SectionPlan,
        frozen_doc_plan: FrozenDocPlan,
        warnings: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        if section_plan.needs_human_confirmation:
            raise ValueError("section 仍需人工确认，不能生成草稿")
        if not section_plan.required_evidence_ids:
            raise ValueError("section 缺少 required_evidence_ids")

        evidence_by_id = {item.evidence_id: item for item in state.evidence_map}
        allowed_product_ids = set(
            frozen_doc_plan.evidence_policy.get("allowed_product_evidence_ids", [])
        )
        reference_ids = set(
            frozen_doc_plan.evidence_policy.get("allowed_reference_style_ids", [])
        )
        trace = frozen_doc_plan.evidence_policy.get("evidence_trace", [])
        bundle: list[dict[str, Any]] = []
        for evidence_id in section_plan.required_evidence_ids:
            item = evidence_by_id.get(evidence_id)
            if item is None:
                raise ValueError(f"required evidence 不存在: {evidence_id}")
            if item.evidence_type == EvidenceType.PRODUCT_SCREENSHOT:
                raise ValueError(
                    "WriterAgent 不得使用截图 evidence 作为产品事实或正文 citation"
                )
            if evidence_id in reference_ids:
                raise ValueError("WriterAgent 不得使用 reference_style evidence")
            if evidence_id not in allowed_product_ids:
                raise ValueError("WriterAgent 使用了未允许的 product evidence")
            if (
                item.corpus_type != CorpusType.PRODUCT_EVIDENCE
                or item.allowed_usage != AllowedUsage.FACTUAL_EVIDENCE
            ):
                raise ValueError("WriterAgent 只能使用 product_evidence/factual_evidence")
            quote = self._quote_for_evidence(item, trace)
            if not quote:
                quote = item.summary or ""
                if not quote.strip():
                    raise ValueError("evidence_trace 缺少 quote 且 EvidenceItem.summary 为空")
                if warnings is not None:
                    warnings.append(f"evidence {evidence_id} 缺少 trace quote，使用 summary。")
            bundle.append(self._bundle_item(item, quote))
        return bundle

    @staticmethod
    def _quote_for_evidence(evidence_item: EvidenceItem, trace: list[Any]) -> str:
        for trace_item in trace:
            if not isinstance(trace_item, dict):
                continue
            if trace_item.get("evidence_id") != evidence_item.evidence_id:
                continue
            if trace_item.get("source_id") != evidence_item.source_id:
                raise ValueError("evidence_trace source_id 不匹配")
            if trace_item.get("corpus_type") != CorpusType.PRODUCT_EVIDENCE.value:
                raise ValueError("evidence_trace corpus_type 不正确")
            if trace_item.get("allowed_usage") != AllowedUsage.FACTUAL_EVIDENCE.value:
                raise ValueError("evidence_trace allowed_usage 不正确")
            quote = trace_item.get("quote")
            if not isinstance(quote, str) or not quote.strip():
                raise ValueError("evidence_trace quote 不合法")
            if quote not in WriterAgent._evidence_text_for_quote_check(evidence_item):
                raise ValueError("evidence_trace quote 不存在于 EvidenceItem")
            return quote
        return ""

    @staticmethod
    def _evidence_text_for_quote_check(item: EvidenceItem) -> str:
        return "\n".join(
            [
                item.summary or "",
                json.dumps(item.extracted_facts, ensure_ascii=False),
            ]
        )

    @staticmethod
    def _bundle_item(item: EvidenceItem, quote: str) -> dict[str, Any]:
        return {
            "evidence_id": item.evidence_id,
            "source_id": item.source_id,
            "summary": item.summary or "",
            "quote": quote,
            "extracted_facts": item.extracted_facts,
            "evidence_type": item.evidence_type.value,
            "confidence": item.confidence,
        }

    def _generate_section_draft(
        self,
        frozen_doc_plan: FrozenDocPlan,
        section_plan: SectionPlan,
        evidence_bundle: list[dict[str, Any]],
    ) -> dict[str, Any]:
        assert self.llm_provider is not None
        payload = self._build_writer_prompt_payload(
            frozen_doc_plan,
            section_plan,
            evidence_bundle,
        )
        return self.llm_provider.generate_json(
            [
                LLMMessage(role="system", content=load_prompt("writer_v1_section.md")),
                LLMMessage(
                    role="user",
                    content=json.dumps(payload, ensure_ascii=False, indent=2),
                ),
            ]
        )

    @staticmethod
    def _build_writer_prompt_payload(
        frozen_doc_plan: FrozenDocPlan,
        section_plan: SectionPlan,
        evidence_bundle: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return {
            "section_plan": WriterAgent._safe_section_plan_payload(section_plan),
            "frozen_doc_plan_summary": (
                WriterAgent._safe_frozen_doc_plan_summary_payload(frozen_doc_plan)
            ),
            "evidence_bundle": evidence_bundle,
            "writing_constraints": section_plan.writing_constraints,
            "writing_style_summary": WriterAgent._safe_writing_style_payload(
                frozen_doc_plan
            ),
        }

    @staticmethod
    def _safe_section_plan_payload(section_plan: SectionPlan) -> dict[str, Any]:
        return {
            "section_id": section_plan.section_id,
            "chapter_title": section_plan.chapter_title,
            "section_title": section_plan.section_title,
            "section_level": section_plan.section_level,
            "parent_section_title": section_plan.parent_section_title,
            "section_path": list(section_plan.section_path),
            "writing_goal": section_plan.writing_goal,
            "required_evidence_ids": list(section_plan.required_evidence_ids),
            "required_capability_ids": list(section_plan.required_capability_ids),
            "required_fact_ids": list(section_plan.required_fact_ids),
            "needs_human_confirmation": section_plan.needs_human_confirmation,
            "writing_constraints": list(section_plan.writing_constraints),
        }

    @staticmethod
    def _safe_frozen_doc_plan_summary_payload(
        frozen_doc_plan: FrozenDocPlan,
    ) -> dict[str, Any]:
        software_identity = frozen_doc_plan.software_identity
        template_decision = frozen_doc_plan.template_decision
        chapter_policy = frozen_doc_plan.chapter_policy
        return {
            "plan_id": frozen_doc_plan.plan_id,
            "target_product_name": WriterAgent._safe_string(
                software_identity.get("target_product_name"),
                "",
            ),
            "target_doc_type": WriterAgent._safe_string(
                software_identity.get("target_doc_type"),
                "",
            ),
            "output_format": WriterAgent._safe_string(
                software_identity.get("output_format"),
                "",
            ),
            "base_template_id": WriterAgent._safe_string(
                template_decision.get("base_template_id"),
                "",
            ),
            "base_template_name": WriterAgent._safe_string(
                template_decision.get("base_template_name"),
                "",
            ),
            "locked_top_level_chapters": WriterAgent._strings_or_default(
                chapter_policy.get("locked_top_level_chapters"),
                [],
            ),
        }

    @staticmethod
    def _safe_writing_style_payload(frozen_doc_plan: FrozenDocPlan) -> dict[str, Any]:
        policy = frozen_doc_plan.writing_policy
        return {
            "writing_style_summary": WriterAgent._safe_string(
                policy.get(
                    "writing_style_summary",
                ),
                "用户操作手册型软著文档，语言客观、克制，不使用宣传式表达。",
            ),
            "operation_step_style": WriterAgent._safe_string(
                policy.get(
                    "operation_step_style",
                ),
                "按用户操作顺序描述入口、页面、操作和结果。",
            ),
            "screenshot_caption_style": WriterAgent._safe_string(
                policy.get(
                    "screenshot_caption_style",
                ),
                "截图说明仅描述界面位置和功能，不作为产品事实来源。",
            ),
            "reference_style_usage_rule": WriterAgent._safe_string(
                policy.get(
                    "reference_style_usage_rule",
                ),
                "reference_style 只允许用于写法和结构，不得作为产品事实。",
            ),
            "forbidden_content_rules": WriterAgent._strings_or_default(
                policy.get("forbidden_content_rules"),
                [
                    "不得使用 reference_style 作为产品事实",
                    "不得把 planned / unknown 写成当前已实现",
                    "不得写 unsupported 功能",
                    "不得自行发明模块、页面、流程",
                    "不得使用宣传式夸大表达",
                ],
            ),
        }

    @staticmethod
    def _safe_string(value: Any, default: str) -> str:
        if isinstance(value, str) and value.strip():
            return value
        return default

    @staticmethod
    def _strings_or_default(value: Any, default: list[str]) -> list[str]:
        if not isinstance(value, list):
            return list(default)
        result = [item for item in value if isinstance(item, str) and item.strip()]
        return result or list(default)

    @staticmethod
    def _project_section_draft(
        section_draft: dict[str, Any],
        section_plan: SectionPlan,
    ) -> dict[str, Any]:
        return {
            "section_id": section_plan.section_id,
            "section_title": section_plan.section_title,
            "section_level": section_plan.section_level,
            "section_path": section_plan.section_path,
            "writing_goal": section_plan.writing_goal,
            "content": str(section_draft["content"]),
            "required_evidence_ids": section_plan.required_evidence_ids,
            "evidence_ids_used": list(section_draft["evidence_ids_used"]),
            "required_capability_ids": section_plan.required_capability_ids,
            "required_fact_ids": section_plan.required_fact_ids,
            "citations": list(section_draft["citations"]),
            "generation_status": "generated",
            "warnings": list(section_draft.get("warnings", [])),
        }

    @staticmethod
    def _build_draft_chapters(
        state: DocForgeState,
        draft_sections_by_id: dict[str, dict[str, Any]],
    ) -> list[dict[str, Any]]:
        assert state.outline is not None
        chapters: list[dict[str, Any]] = []
        for chapter in state.outline.chapters:
            chapter_sections: list[dict[str, Any]] = []
            for node in iter_outline_sections(
                type(state.outline)(
                    based_on_plan_id=state.outline.based_on_plan_id,
                    outline_id=state.outline.outline_id,
                    chapters=[chapter],
                    required_evidence=state.outline.required_evidence,
                    required_screenshots=state.outline.required_screenshots,
                )
            ):
                section_id = str(node.section.get("section_id", ""))
                draft_section = draft_sections_by_id.get(section_id)
                if draft_section is None:
                    raise ValueError(f"draft section 缺失: {section_id}")
                chapter_sections.append(draft_section)
            chapters.append(
                {
                    "chapter_id": str(chapter.get("chapter_id", "")),
                    "title": str(chapter.get("title", "")),
                    "level": 1,
                    "sections": chapter_sections,
                }
            )
        return chapters
