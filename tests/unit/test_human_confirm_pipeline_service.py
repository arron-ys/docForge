from pathlib import Path

import pytest

from docforge_core.agents.frozen_doc_plan_service import FrozenDocPlanService
from docforge_core.agents.human_confirm_gate import HumanConfirmGate
from docforge_core.agents.human_confirm_pipeline_service import HumanConfirmPipelineService
from docforge_core.domain.enums import (
    CapabilityType,
    ImplementationStatus,
    NextAction,
    WorkflowStatus,
)
from docforge_core.domain.schemas import DiagnosisResult, ProductProfile, TemplateStrategy

from .agent_helpers import capability, product_evidence, reference_evidence, save_state


def _pipeline_state(tmp_path: Path, risk_chapters: list[str] | None = None):
    store, state = save_state(
        tmp_path,
        WorkflowStatus.TEMPLATE_RECOMMENDED,
        [product_evidence(), reference_evidence()],
    )
    state.diagnosis_result = DiagnosisResult(primary_type="Web/SaaS 平台")
    state.template_strategy = TemplateStrategy(
        base_template_id="TEMPLATE_WEB",
        base_template_name="Web 模板",
        recommended_chapters=["引言", "核心功能说明"],
        risk_chapters=risk_chapters or [],
    )
    state.product_capabilities = [
        capability("cap_current", CapabilityType.DATASET_MANAGEMENT, name="数据集管理"),
        capability(
            "cap_planned",
            CapabilityType.AI_TRAINING,
            ImplementationStatus.PLANNED,
            name="模型训练",
        ),
    ]
    state.product_profile = ProductProfile(uncertain_features=["证据不足：秘密功能"])
    store.save_state(state)
    pipeline = HumanConfirmPipelineService(
        human_confirm_gate=HumanConfirmGate(store),
        frozen_doc_plan_service=FrozenDocPlanService(store),
    )
    return pipeline, state.run_id


def test_accept_recommendation_and_freeze_reaches_plan_frozen(tmp_path: Path) -> None:
    pipeline, run_id = _pipeline_state(tmp_path)

    result = pipeline.accept_recommendation_and_freeze(run_id, user_notes="接受")

    assert result.workflow_status == WorkflowStatus.PLAN_FROZEN
    assert result.next_action == NextAction.CREATE_OUTLINE
    assert result.frozen_doc_plan is not None
    assert result.outline is None
    assert result.draft_versions == []
    assert "数据集管理" in result.frozen_doc_plan.feature_policy["allowed_current_feature_names"]
    assert "模型训练" not in result.frozen_doc_plan.feature_policy["allowed_current_feature_names"]
    assert all(
        item["corpus_type"] == "product_evidence"
        for item in result.frozen_doc_plan.evidence_policy["evidence_trace"]
    )


def test_pipeline_requires_risk_acknowledgement(tmp_path: Path) -> None:
    pipeline, run_id = _pipeline_state(tmp_path, ["AI 能力当前版本状态待确认"])

    with pytest.raises(ValueError, match="风险"):
        pipeline.accept_recommendation_and_freeze(run_id)


def test_pipeline_can_freeze_after_risk_acknowledgement(tmp_path: Path) -> None:
    pipeline, run_id = _pipeline_state(tmp_path, ["AI 能力当前版本状态待确认"])

    result = pipeline.accept_recommendation_and_freeze(run_id, risk_acknowledged=True)

    assert result.workflow_status == WorkflowStatus.PLAN_FROZEN
    assert result.frozen_doc_plan is not None
    assert result.frozen_doc_plan.template_decision["risk_acknowledged"] is True
    assert result.frozen_doc_plan.template_decision["selected_top_level_chapters"] == [
        "引言",
        "核心功能说明",
    ]
    assert result.frozen_doc_plan.template_decision["acknowledged_risk_chapters"] == [
        "AI 能力当前版本状态待确认"
    ]
    assert result.outline is None
    assert result.draft_versions == []
