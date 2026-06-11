"""Conditional auto-confirmation for product type and document strategy."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from docforge_core.domain.enums import (
    AllowedUsage,
    CorpusType,
    EvidenceType,
    FileType,
    SourceType,
    WorkflowStatus,
)
from docforge_core.domain.schemas import DocForgeState, TemplateConfirmationDecision

from .run_settings import (
    doc_output_type_label,
    get_run_settings,
    product_type_label,
    reference_style_strength_label,
)

MIN_AUTO_CONFIRM_CONFIDENCE = 0.6


@dataclass(slots=True)
class AutoConfirmationDecision:
    can_auto_confirm: bool
    reason: str
    conflicts: list[str] = field(default_factory=list)
    selected_product_type: str = ""
    selected_doc_type: str = ""
    selected_reference_style_strength: str = ""
    recommended_product_type: str = ""
    user_selected_product_type: str = ""
    product_type_conflict: bool = False
    confidence: float | None = None
    confirmation_payload: TemplateConfirmationDecision | None = None
    message: str = ""

    def as_metadata(self) -> dict[str, Any]:
        return {
            "can_auto_confirm": self.can_auto_confirm,
            "reason": self.reason,
            "conflicts": list(self.conflicts),
            "selected_product_type": self.selected_product_type,
            "selected_doc_type": self.selected_doc_type,
            "selected_reference_style_strength": self.selected_reference_style_strength,
            "recommended_product_type": self.recommended_product_type,
            "user_selected_product_type": self.user_selected_product_type,
            "product_type_conflict": self.product_type_conflict,
            "confidence": self.confidence,
            "message": self.message,
        }


class AutoConfirmationPolicy:
    """Decide whether USER_CONFIRM_REQUIRED can be confirmed without manual input."""

    def evaluate(self, state: DocForgeState) -> AutoConfirmationDecision:
        settings = get_run_settings(state)
        selected_doc_type = doc_output_type_label(settings["doc_output_type"])
        selected_reference_style = reference_style_strength_label(
            settings["reference_style_strength"]
        )
        user_type_hint = settings["product_type_hint"]
        user_selected_product_type = product_type_label(user_type_hint)

        base_decision = AutoConfirmationDecision(
            can_auto_confirm=False,
            reason="当前需要人工确认。",
            selected_doc_type=selected_doc_type,
            selected_reference_style_strength=selected_reference_style,
            user_selected_product_type=user_selected_product_type,
        )

        if state.workflow_status != WorkflowStatus.USER_CONFIRM_REQUIRED:
            return self._blocked(base_decision, "当前状态不需要产品类型和文档策略确认。")

        source_reason = self._source_block_reason(state)
        if source_reason:
            return self._blocked(base_decision, source_reason)

        if state.template_strategy is None:
            return self._blocked(base_decision, "系统尚未生成文档策略推荐。")
        if state.diagnosis_result is None:
            return self._blocked(base_decision, "系统尚未完成产品类型判断。")

        recommended_product_type = str(state.diagnosis_result.primary_type or "").strip()
        base_decision.recommended_product_type = recommended_product_type
        if not recommended_product_type or recommended_product_type == "待确认":
            return self._blocked(base_decision, "产品类型判断结果不明确，需要人工确认。")

        confidence = state.diagnosis_result.primary_type_confidence
        base_decision.confidence = confidence
        if confidence is not None and confidence < MIN_AUTO_CONFIRM_CONFIDENCE:
            return self._blocked(base_decision, "产品类型判断置信度不足，需要人工确认。")

        if not state.template_strategy.recommended_chapters:
            return self._blocked(base_decision, "推荐文档策略缺少一级章节，需要人工确认。")
        if state.template_strategy.risk_chapters:
            return self._blocked(base_decision, "推荐策略包含风险章节，需要人工确认。")
        if state.blocker_issues:
            return self._blocked(base_decision, "当前存在阻塞问题，需要人工确认。")

        boundary_reason = self._evidence_boundary_block_reason(state)
        if boundary_reason:
            return self._blocked(base_decision, boundary_reason)

        recommended_option = product_type_option_for_diagnosis(recommended_product_type)
        if user_type_hint != "agent_decide":
            if recommended_option is None or user_type_hint != recommended_option:
                base_decision.product_type_conflict = True
                base_decision.conflicts.append(
                    f"系统判断为“{recommended_product_type}”，但你当前选择的是“{user_selected_product_type}”。"
                )
                return self._blocked(
                    base_decision,
                    "系统判断结果与你当前选择不一致，请人工确认采用哪一种产品类型。",
                )
            selected_product_type = user_selected_product_type
            product_message = f"产品类型：采用你选择的“{selected_product_type}”，与资料判断一致。"
        else:
            selected_product_type = recommended_product_type
            product_message = (
                f"产品类型：由 Agent 根据自有产品资料判断为“{recommended_product_type}”。"
            )

        confirmation_payload = build_confirmation_payload(
            state,
            user_note=(
                "系统根据当前资料和右侧策略偏好自动确认。"
                f"产品类型={selected_product_type}；"
                f"文档类型={selected_doc_type}；参考风格={selected_reference_style}。"
            ),
        )
        message = (
            "已根据当前资料自动确认产品类型和文档策略：\n\n"
            f"{product_message}\n"
            f"文档类型：{selected_doc_type}\n"
            f"参考风格：{selected_reference_style}\n\n"
            "系统将继续生成软著文档。"
        )
        return AutoConfirmationDecision(
            can_auto_confirm=True,
            reason="右侧策略偏好与系统判断无冲突，且资料边界满足自动确认条件。",
            selected_product_type=selected_product_type,
            selected_doc_type=selected_doc_type,
            selected_reference_style_strength=selected_reference_style,
            recommended_product_type=recommended_product_type,
            user_selected_product_type=user_selected_product_type,
            product_type_conflict=False,
            confidence=confidence,
            confirmation_payload=confirmation_payload,
            message=message,
        )

    @staticmethod
    def _blocked(
        decision: AutoConfirmationDecision,
        reason: str,
    ) -> AutoConfirmationDecision:
        decision.reason = reason
        return decision

    @staticmethod
    def _source_block_reason(state: DocForgeState) -> str:
        if not state.source_registry:
            return "尚未上传资料，不能自动确认。"

        references = [
            source
            for source in state.source_registry
            if source.source_type == SourceType.REFERENCE_SOFT_COPYRIGHT_DOC
        ]
        screenshots = [
            source
            for source in state.source_registry
            if source.source_type == SourceType.SCREENSHOT
            or source.allowed_usage == AllowedUsage.DISPLAY_MATERIAL_ONLY
        ]
        product_documents = [
            source
            for source in state.source_registry
            if source.is_product_source
            and source.allowed_usage == AllowedUsage.FACTUAL_EVIDENCE
            and source.source_type != SourceType.SCREENSHOT
            and source.file_type in {FileType.DOCX, FileType.PDF, FileType.MD, FileType.TXT, FileType.HTML}
        ]
        if references and len(references) == len(state.source_registry):
            return "当前只有外部参考资料，不能自动确认产品类型。"
        if screenshots and len(screenshots) == len(state.source_registry):
            return "当前只有产品截图，不能自动确认产品类型。"
        if not product_documents:
            return "缺少可作为事实依据的自有产品文档，不能自动确认。"
        return ""

    @staticmethod
    def _evidence_boundary_block_reason(state: DocForgeState) -> str:
        for item in state.evidence_map:
            if (
                item.corpus_type == CorpusType.PRODUCT_EVIDENCE
                and item.allowed_usage == AllowedUsage.FACTUAL_EVIDENCE
                and item.source_type == SourceType.REFERENCE_SOFT_COPYRIGHT_DOC
            ):
                return "检测到外部参考资料被标记为产品事实证据，需要人工确认。"
            if (
                item.allowed_usage == AllowedUsage.FACTUAL_EVIDENCE
                and (
                    item.source_type == SourceType.SCREENSHOT
                    or item.evidence_type == EvidenceType.PRODUCT_SCREENSHOT
                )
            ):
                return "检测到产品截图被标记为事实证据，需要人工确认。"
        return ""


def build_confirmation_payload(
    state: DocForgeState,
    *,
    user_note: str | None = None,
) -> TemplateConfirmationDecision:
    strategy = state.template_strategy
    if strategy is None:
        raise ValueError("构造确认决策要求存在 template_strategy")
    return TemplateConfirmationDecision(
        accepted_recommendation=True,
        selected_base_template_id=strategy.base_template_id,
        selected_base_template_name=strategy.base_template_name,
        selected_enhancement_pack_ids=list(strategy.enhancement_pack_ids),
        selected_top_level_chapters=list(strategy.recommended_chapters),
        selected_optional_chapters=[],
        acknowledged_risk_chapters=list(strategy.risk_chapters),
        excluded_chapters=[],
        risk_acknowledged=bool(strategy.risk_chapters),
        user_notes=user_note,
    )


def product_type_option_for_diagnosis(primary_type: str) -> str | None:
    value = primary_type.lower()
    if "saas" in value or "web" in value:
        return "saas_web_platform"
    if "ai" in value or "智能" in primary_type:
        return "ai_platform"
    if "数据" in primary_type:
        return "data_platform"
    if "工业" in primary_type or "汽车" in primary_type:
        return "industrial_software"
    if "工具" in primary_type or "通用软件" in primary_type or "通用软件系统" in primary_type:
        return "tool_software"
    return None
