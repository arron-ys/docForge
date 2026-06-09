"""Diagnose software type from validated ProductCapability records."""

from __future__ import annotations

from docforge_core.domain.enums import (
    CapabilityType,
    ImplementationStatus,
    NextAction,
    ValidationStatus,
    WorkflowStatus,
)
from docforge_core.domain.schemas import DiagnosisResult, DocForgeState, ProductCapability
from docforge_core.io.state_store import StateStore
from docforge_core.llm.base import LLMProvider

from ._shared import AI_NON_CURRENT_RISK_PREFIX, transition, unique_strings

DATA_TYPES = {
    CapabilityType.DATA_MANAGEMENT,
    CapabilityType.DATASET_MANAGEMENT,
    CapabilityType.DATA_QUALITY,
    CapabilityType.ANNOTATION,
}
AI_TYPES = {
    CapabilityType.AI_TRAINING,
    CapabilityType.AI_INFERENCE,
    CapabilityType.AI_EVALUATION,
    CapabilityType.MODEL_ASSET_MANAGEMENT,
}
PERMISSION_TYPES = {CapabilityType.PERMISSION_MANAGEMENT, CapabilityType.USER_MANAGEMENT}
AUTOMOTIVE_TYPES = {
    CapabilityType.AUTOMOTIVE_DOMAIN,
    CapabilityType.SIMULATION_MANAGEMENT,
    CapabilityType.THREE_D_MODEL_MANAGEMENT,
    CapabilityType.CAD_MODEL_MANAGEMENT,
}


class SoftwareDiagnosisAgent:
    """Use only validated capabilities; raw evidence text is outside this boundary."""

    def __init__(
        self,
        state_store: StateStore | None = None,
        llm_provider: LLMProvider | None = None,
    ) -> None:
        self.state_store = state_store or StateStore()
        self.llm_provider = llm_provider

    def diagnose_run(self, run_id: str) -> DocForgeState:
        state = self.state_store.load_state(run_id)
        state.diagnosis_result = self._diagnose(state)
        transition(
            state,
            WorkflowStatus.PRODUCT_UNDERSTOOD,
            WorkflowStatus.DIAGNOSED,
            NextAction.RECOMMEND_TEMPLATE,
            "SoftwareDiagnosisAgent.diagnose_run",
            "software type diagnosed",
        )
        self.state_store.save_state(state)
        return state

    @staticmethod
    def _diagnose(state: DocForgeState) -> DiagnosisResult:
        validated = [
            item
            for item in state.product_capabilities
            if item.validation_status == ValidationStatus.VALIDATED
        ]
        current = [
            item for item in validated if item.implementation_status == ImplementationStatus.CURRENT
        ]
        non_current = [
            item
            for item in validated
            if item.implementation_status in {ImplementationStatus.PLANNED, ImplementationStatus.UNKNOWN}
        ]
        if not current:
            return DiagnosisResult(
                primary_type="待确认",
                primary_type_confidence=0.3,
                recommended_doc_style="待用户补充资料后确认",
                diagnosis_reasons=["缺少已验证的当前版本产品能力证据。"],
                risk_notes=unique_strings(
                    [
                        "缺少已验证的当前版本产品能力证据。",
                        *SoftwareDiagnosisAgent._risk_notes(non_current),
                    ]
                ),
            )

        current_types = {item.capability_type for item in current}
        if CapabilityType.WEB_SAAS in current_types:
            primary_type = "Web/SaaS 平台"
            recommended_style = "用户操作手册型软著文档"
            confidence = 0.85
        else:
            primary_type = "通用软件系统"
            recommended_style = "功能说明型软著文档"
            confidence = 0.65

        enhancement_tags: list[str] = []
        if current_types.intersection(DATA_TYPES):
            enhancement_tags.append("数据平台")
        if current_types.intersection(AI_TYPES):
            enhancement_tags.append("AI 平台")
        if current_types.intersection(PERMISSION_TYPES):
            enhancement_tags.append("权限管理")
        if current_types.intersection(AUTOMOTIVE_TYPES):
            enhancement_tags.append("汽车工业软件")

        reasons = [
            f"基于已验证能力 {item.capability_id}，识别 {item.capability_type.value} 能力。"
            for item in current
        ]
        return DiagnosisResult(
            primary_type=primary_type,
            primary_type_confidence=confidence,
            business_objects=state.product_profile.business_objects,
            enhancement_tags=enhancement_tags,
            recommended_doc_style=recommended_style,
            alternative_doc_styles=(
                ["功能说明型软著文档"] if primary_type == "Web/SaaS 平台" else []
            ),
            diagnosis_reasons=reasons,
            risk_notes=SoftwareDiagnosisAgent._risk_notes(non_current),
        )

    @staticmethod
    def _risk_notes(capabilities: list[ProductCapability]) -> list[str]:
        notes = [
            f"能力 {item.capability_id}（{item.name}）为 {item.implementation_status.value}，"
            "不作为当前版本能力。"
            for item in capabilities
        ]
        ai_capability_ids = [
            item.capability_id for item in capabilities if item.capability_type in AI_TYPES
        ]
        if ai_capability_ids:
            notes.append(
                f"{AI_NON_CURRENT_RISK_PREFIX}依据：{', '.join(ai_capability_ids)}。"
            )
        return unique_strings(notes)
