from pathlib import Path

import pytest

from docforge_core.agents.product_understanding_agent import ProductUnderstandingAgent
from docforge_core.agents.reference_style_agent import ReferenceStyleAgent
from docforge_core.agents.software_diagnosis_agent import SoftwareDiagnosisAgent
from docforge_core.agents.template_strategy_agent import TemplateStrategyAgent
from docforge_core.agents.understanding_pipeline_service import UnderstandingPipelineService
from docforge_core.domain.enums import CapabilityType, ImplementationStatus, WorkflowStatus
from docforge_core.llm.mock_provider import MockLLMProvider

from .agent_helpers import (
    accepting_verifier_response,
    product_evidence,
    reference_evidence,
    save_state,
)


def _pipeline(tmp_path: Path, status: ImplementationStatus = ImplementationStatus.CURRENT):
    quote = (
        "未来规划中将支持模型训练"
        if status == ImplementationStatus.PLANNED
        else "当前版本支持模型推理服务"
    )
    store, state = save_state(
        tmp_path,
        WorkflowStatus.EVIDENCE_MAPPED,
        [reference_evidence(), product_evidence(summary=quote)],
    )
    response = {
        "capabilities": [
            {
                "name": "模型能力",
                "description": "模型能力",
                "capability_type": (
                    CapabilityType.AI_TRAINING.value
                    if status == ImplementationStatus.PLANNED
                    else CapabilityType.AI_INFERENCE.value
                ),
                "implementation_status": status.value,
                "supporting_evidence_ids": ["ev_product"],
                "supporting_quotes": [quote],
                "confidence": 0.9,
            }
        ]
    }
    product_provider = MockLLMProvider(
        json_responses=[response, accepting_verifier_response(response)]
    )
    return (
        UnderstandingPipelineService(
            reference_style_agent=ReferenceStyleAgent(
                state_store=store,
                llm_provider=MockLLMProvider(json_response={}),
            ),
            product_understanding_agent=ProductUnderstandingAgent(
                state_store=store, llm_provider=product_provider
            ),
            software_diagnosis_agent=SoftwareDiagnosisAgent(state_store=store),
            template_strategy_agent=TemplateStrategyAgent(state_store=store),
        ),
        state.run_id,
    )


def test_pipeline_runs_to_template_recommended_with_capabilities(tmp_path: Path) -> None:
    pipeline, run_id = _pipeline(tmp_path)

    state = pipeline.run_until_template_recommended(run_id)

    assert state.workflow_status == WorkflowStatus.TEMPLATE_RECOMMENDED
    assert state.product_capabilities
    assert state.frozen_doc_plan is None
    assert state.outline is None
    assert state.draft_versions == []


def test_pipeline_planned_ai_does_not_add_ai_pack(tmp_path: Path) -> None:
    pipeline, run_id = _pipeline(tmp_path, ImplementationStatus.PLANNED)

    state = pipeline.run_until_template_recommended(run_id)

    assert state.template_strategy is not None
    assert "PACK_AI_LIGHT" not in state.template_strategy.enhancement_pack_ids


def test_pipeline_requires_evidence_mapped_status(tmp_path: Path) -> None:
    pipeline, run_id = _pipeline(tmp_path)
    state = pipeline.reference_style_agent.state_store.load_state(run_id)
    state.workflow_status = WorkflowStatus.SOURCE_PARSED
    pipeline.reference_style_agent.state_store.save_state(state)

    with pytest.raises(ValueError, match="EVIDENCE_MAPPED"):
        pipeline.run_until_template_recommended(run_id)


def test_pipeline_semantic_rejection_does_not_add_ai_pack(tmp_path: Path) -> None:
    quote = "当前版本支持三维模型导入与查看"
    store, state = save_state(
        tmp_path,
        WorkflowStatus.EVIDENCE_MAPPED,
        [product_evidence(summary=quote)],
    )
    extraction = {
        "capabilities": [
            {
                "name": "AI模型训练",
                "description": "AI模型训练",
                "capability_type": CapabilityType.AI_TRAINING.value,
                "implementation_status": ImplementationStatus.CURRENT.value,
                "supporting_evidence_ids": ["ev_product"],
                "supporting_quotes": [quote],
                "confidence": 0.9,
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
    pipeline = UnderstandingPipelineService(
        reference_style_agent=ReferenceStyleAgent(state_store=store),
        product_understanding_agent=ProductUnderstandingAgent(
            state_store=store,
            llm_provider=MockLLMProvider(json_responses=[extraction, rejection]),
        ),
        software_diagnosis_agent=SoftwareDiagnosisAgent(state_store=store),
        template_strategy_agent=TemplateStrategyAgent(state_store=store),
    )

    result = pipeline.run_until_template_recommended(state.run_id)

    assert result.product_capabilities == []
    assert result.template_strategy is not None
    assert "PACK_AI_LIGHT" not in result.template_strategy.enhancement_pack_ids


def test_pipeline_rejected_profile_entity_does_not_affect_downstream(tmp_path: Path) -> None:
    quote = "当前版本支持三维模型导入与查看"
    store, state = save_state(
        tmp_path,
        WorkflowStatus.EVIDENCE_MAPPED,
        [product_evidence(summary=quote)],
    )
    extraction = {
        "capabilities": [
            {
                "name": "三维模型导入与查看",
                "description": "三维模型导入与查看",
                "capability_type": CapabilityType.THREE_D_MODEL_MANAGEMENT.value,
                "implementation_status": ImplementationStatus.CURRENT.value,
                "supporting_evidence_ids": ["ev_product"],
                "supporting_quotes": [quote],
                "confidence": 0.9,
            }
        ],
        "business_objects": [
            {
                "name": "AI训练任务",
                "supporting_evidence_ids": ["ev_product"],
                "supporting_quotes": [quote],
            }
        ],
    }
    entity_rejection = {
        "results": [
            {
                "entity_index": 0,
                "supported": False,
                "name_supported": False,
                "entity_type_supported": False,
                "reason": "quote 不支持 AI训练任务",
            }
        ]
    }
    provider = MockLLMProvider(
        json_responses=[
            extraction,
            accepting_verifier_response(extraction),
            entity_rejection,
        ]
    )
    pipeline = UnderstandingPipelineService(
        reference_style_agent=ReferenceStyleAgent(state_store=store),
        product_understanding_agent=ProductUnderstandingAgent(
            state_store=store,
            llm_provider=provider,
        ),
        software_diagnosis_agent=SoftwareDiagnosisAgent(state_store=store),
        template_strategy_agent=TemplateStrategyAgent(state_store=store),
    )

    result = pipeline.run_until_template_recommended(state.run_id)

    assert "AI训练任务" not in result.product_profile.business_objects
    assert result.diagnosis_result is not None
    assert "AI训练任务" not in result.diagnosis_result.business_objects
    assert result.template_strategy is not None
    assert "PACK_AI_LIGHT" not in result.template_strategy.enhancement_pack_ids
    assert provider.json_call_count == 3


def test_pipeline_planned_profile_entity_stays_out_of_current_profile_and_diagnosis(
    tmp_path: Path,
) -> None:
    quote = "未来规划中将支持数据交易市场"
    store, state = save_state(
        tmp_path,
        WorkflowStatus.EVIDENCE_MAPPED,
        [product_evidence(summary=quote)],
    )
    extraction = {
        "capabilities": [],
        "business_objects": [
            {
                "name": "数据交易市场",
                "implementation_status": ImplementationStatus.CURRENT.value,
                "supporting_evidence_ids": ["ev_product"],
                "supporting_quotes": [quote],
            }
        ],
    }
    status_correction = {
        "results": [
            {
                "entity_index": 0,
                "supported": True,
                "name_supported": True,
                "entity_type_supported": True,
                "implementation_status_supported": False,
                "corrected_implementation_status": ImplementationStatus.PLANNED.value,
                "reason": "quote 表达的是规划状态",
            }
        ]
    }
    provider = MockLLMProvider(json_responses=[extraction, status_correction])
    pipeline = UnderstandingPipelineService(
        reference_style_agent=ReferenceStyleAgent(state_store=store),
        product_understanding_agent=ProductUnderstandingAgent(
            state_store=store,
            llm_provider=provider,
        ),
        software_diagnosis_agent=SoftwareDiagnosisAgent(state_store=store),
        template_strategy_agent=TemplateStrategyAgent(state_store=store),
    )

    result = pipeline.run_until_template_recommended(state.run_id)

    assert result.product_profile.business_objects == []
    assert "规划中：数据交易市场" in result.product_profile.uncertain_features
    assert result.diagnosis_result is not None
    assert result.diagnosis_result.business_objects == []
    assert provider.json_call_count == 2
