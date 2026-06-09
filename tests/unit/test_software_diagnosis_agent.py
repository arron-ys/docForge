from pathlib import Path

from docforge_core.agents.product_understanding_agent import ProductUnderstandingAgent
from docforge_core.agents.software_diagnosis_agent import SoftwareDiagnosisAgent
from docforge_core.domain.enums import (
    CapabilityType,
    ImplementationStatus,
    NextAction,
    WorkflowStatus,
)
from docforge_core.domain.schemas import ProductCapability, ProductProfile
from docforge_core.llm.mock_provider import MockLLMProvider

from .agent_helpers import capability, product_evidence, save_state


def _diagnose(tmp_path: Path, capabilities: list[ProductCapability]):
    store, state = save_state(tmp_path, WorkflowStatus.PRODUCT_UNDERSTOOD)
    state.product_capabilities = capabilities
    store.save_state(state)
    return SoftwareDiagnosisAgent(state_store=store).diagnose_run(state.run_id)


def test_diagnosis_uses_validated_current_capabilities_only(tmp_path: Path) -> None:
    result = _diagnose(
        tmp_path,
        [capability("cap_dataset", CapabilityType.DATASET_MANAGEMENT, name="数据集管理")],
    )

    assert result.diagnosis_result is not None
    assert "数据平台" in result.diagnosis_result.enhancement_tags


def test_planned_ai_capability_only_goes_to_risk_notes(tmp_path: Path) -> None:
    result = _diagnose(
        tmp_path,
        [
            capability(
                "cap_ai_planned",
                CapabilityType.AI_TRAINING,
                ImplementationStatus.PLANNED,
                name="模型训练",
            )
        ],
    )

    assert result.diagnosis_result is not None
    assert "AI 平台" not in result.diagnosis_result.enhancement_tags
    assert any("AI 能力仅出现在规划中" in item for item in result.diagnosis_result.risk_notes)
    assert all(
        "cap_ai_planned" in item
        for item in result.diagnosis_result.risk_notes
        if "模型训练" in item or "AI 能力" in item
    )


def test_current_ai_capability_adds_ai_platform(tmp_path: Path) -> None:
    result = _diagnose(tmp_path, [capability("cap_ai", CapabilityType.AI_INFERENCE)])
    assert result.diagnosis_result is not None
    assert "AI 平台" in result.diagnosis_result.enhancement_tags


def test_3d_model_management_does_not_add_ai_platform(tmp_path: Path) -> None:
    result = _diagnose(tmp_path, [capability("cap_3d", CapabilityType.THREE_D_MODEL_MANAGEMENT)])
    assert result.diagnosis_result is not None
    assert "AI 平台" not in result.diagnosis_result.enhancement_tags


def test_file_import_export_does_not_add_data_platform(tmp_path: Path) -> None:
    result = _diagnose(tmp_path, [capability("cap_file", CapabilityType.FILE_IMPORT_EXPORT)])
    assert result.diagnosis_result is not None
    assert "数据平台" not in result.diagnosis_result.enhancement_tags


def test_diagnosis_reasons_reference_capability_id(tmp_path: Path) -> None:
    result = _diagnose(tmp_path, [capability("cap_dataset", CapabilityType.DATASET_MANAGEMENT)])
    assert result.diagnosis_result is not None
    assert all("cap_" in reason for reason in result.diagnosis_result.diagnosis_reasons)


def test_no_validated_current_capability_results_pending(tmp_path: Path) -> None:
    result = _diagnose(tmp_path, [])
    assert result.diagnosis_result is not None
    assert result.diagnosis_result.primary_type == "待确认"
    assert result.diagnosis_result.primary_type_confidence <= 0.4
    assert "缺少已验证的当前版本产品能力证据。" in result.diagnosis_result.risk_notes
    assert result.workflow_status == WorkflowStatus.DIAGNOSED
    assert result.next_action == NextAction.RECOMMEND_TEMPLATE


def test_semantically_rejected_ai_candidate_does_not_affect_diagnosis(tmp_path: Path) -> None:
    quote = "当前版本支持三维模型导入与查看"
    store, state = save_state(
        tmp_path,
        WorkflowStatus.REFERENCE_STYLE_ANALYZED,
        [product_evidence(summary=quote)],
    )
    extraction = {
        "capabilities": [
            {
                "name": "AI模型训练",
                "capability_type": CapabilityType.AI_TRAINING.value,
                "implementation_status": ImplementationStatus.CURRENT.value,
                "supporting_evidence_ids": ["ev_product"],
                "supporting_quotes": [quote],
            }
        ]
    }
    rejection = {
        "results": [
            {
                "candidate_index": 0,
                "supported": False,
                "name_supported": False,
                "capability_type_supported": False,
                "implementation_status_supported": True,
                "reason": "quote 不支持 AI 模型训练",
            }
        ]
    }
    ProductUnderstandingAgent(
        state_store=store,
        llm_provider=MockLLMProvider(json_responses=[extraction, rejection]),
    ).understand_run(state.run_id)

    result = SoftwareDiagnosisAgent(state_store=store).diagnose_run(state.run_id)

    assert result.diagnosis_result is not None
    assert "AI 平台" not in result.diagnosis_result.enhancement_tags


def test_corrected_3d_capability_does_not_affect_ai_diagnosis(tmp_path: Path) -> None:
    quote = "当前版本支持三维模型导入与查看"
    store, state = save_state(
        tmp_path,
        WorkflowStatus.REFERENCE_STYLE_ANALYZED,
        [product_evidence(summary=quote)],
    )
    extraction = {
        "capabilities": [
            {
                "name": "三维模型导入与查看",
                "capability_type": CapabilityType.AI_TRAINING.value,
                "implementation_status": ImplementationStatus.CURRENT.value,
                "supporting_evidence_ids": ["ev_product"],
                "supporting_quotes": [quote],
            }
        ]
    }
    correction = {
        "results": [
            {
                "candidate_index": 0,
                "supported": True,
                "name_supported": True,
                "capability_type_supported": False,
                "implementation_status_supported": True,
                "corrected_capability_type": CapabilityType.THREE_D_MODEL_MANAGEMENT.value,
                "reason": "应修正为三维模型管理",
            }
        ]
    }
    ProductUnderstandingAgent(
        state_store=store,
        llm_provider=MockLLMProvider(json_responses=[extraction, correction]),
    ).understand_run(state.run_id)

    result = SoftwareDiagnosisAgent(state_store=store).diagnose_run(state.run_id)

    assert result.diagnosis_result is not None
    assert "AI 平台" not in result.diagnosis_result.enhancement_tags
    assert "汽车工业软件" in result.diagnosis_result.enhancement_tags


def test_diagnosis_business_objects_follow_verified_profile_only(tmp_path: Path) -> None:
    store, state = save_state(tmp_path, WorkflowStatus.PRODUCT_UNDERSTOOD)
    state.product_capabilities = [
        capability("cap_dataset", CapabilityType.DATASET_MANAGEMENT, name="数据集管理")
    ]
    state.product_profile = ProductProfile(business_objects=[])
    store.save_state(state)

    result = SoftwareDiagnosisAgent(state_store=store).diagnose_run(state.run_id)

    assert result.diagnosis_result is not None
    assert result.diagnosis_result.business_objects == []
    assert "数据平台" in result.diagnosis_result.enhancement_tags
