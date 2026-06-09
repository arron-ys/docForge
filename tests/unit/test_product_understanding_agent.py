from pathlib import Path
from typing import Any

from docforge_core.agents.capability_grounding_verifier import (
    ProductCapabilityGroundingVerifier,
)
from docforge_core.agents.capability_validation_trace import validate_capability_trace
from docforge_core.agents.product_understanding_agent import (
    MISSING_PRODUCT_QUESTION,
    ProductUnderstandingAgent,
)
from docforge_core.agents.profile_entity_grounding_verifier import (
    ProductProfileEntityGroundingVerifier,
)
from docforge_core.domain.enums import (
    CapabilityType,
    ImplementationStatus,
    NextAction,
    ValidationStatus,
    WorkflowStatus,
)
from docforge_core.domain.schemas import DocForgeState
from docforge_core.io.run_paths import get_run_dir
from docforge_core.llm.mock_provider import MockLLMProvider

from .agent_helpers import (
    accepting_profile_entity_response,
    accepting_verifier_response,
    product_evidence,
    reference_evidence,
    save_state,
)


def _run(
    tmp_path: Path,
    summary: str,
    llm_data: dict[str, Any],
    evidence_id: str = "ev_product",
    verifier_response: dict[str, Any] | None = None,
    profile_entity_response: dict[str, Any] | None = None,
) -> tuple[ProductUnderstandingAgent, DocForgeState]:
    store, state = save_state(
        tmp_path,
        WorkflowStatus.REFERENCE_STYLE_ANALYZED,
        [product_evidence(evidence_id=evidence_id, summary=summary)],
    )
    responses = [llm_data]
    raw_capabilities = llm_data.get("capabilities", [])
    if isinstance(raw_capabilities, list) and raw_capabilities:
        responses.append(verifier_response or accepting_verifier_response(llm_data))
    raw_entities = [
        item
        for field_name in ("business_objects", "target_users", "pages", "workflows")
        for item in (
            llm_data.get(field_name, [])
            if isinstance(llm_data.get(field_name, []), list)
            else []
        )
        if isinstance(item, dict)
    ]
    if raw_entities:
        responses.append(
            profile_entity_response or accepting_profile_entity_response(llm_data)
        )
    agent = ProductUnderstandingAgent(
        state_store=store,
        llm_provider=MockLLMProvider(json_responses=responses),
    )
    return agent, agent.understand_run(state.run_id)


def _candidate(
    name: str,
    capability_type: CapabilityType,
    quote: str,
    evidence_ids: list[str] | None = None,
    status: ImplementationStatus = ImplementationStatus.CURRENT,
) -> dict[str, object]:
    return {
        "name": name,
        "description": name,
        "capability_type": capability_type.value,
        "implementation_status": status.value,
        "supporting_evidence_ids": evidence_ids if evidence_ids is not None else ["ev_product"],
        "supporting_quotes": [quote],
        "confidence": 0.9,
        "reasoning": "基于引用证据",
    }


def _entity(
    name: str,
    quote: str,
    steps: list[str] | None = None,
    status: ImplementationStatus = ImplementationStatus.CURRENT,
) -> dict[str, object]:
    result: dict[str, object] = {
        "name": name,
        "implementation_status": status.value,
        "supporting_evidence_ids": ["ev_product"],
        "supporting_quotes": [quote],
    }
    if steps is not None:
        result["steps"] = steps
    return result


def _entity_result(
    supported: bool,
    reason: str,
    entity_index: int = 0,
) -> dict[str, Any]:
    return {
        "results": [
            {
                "entity_index": entity_index,
                "supported": supported,
                "name_supported": supported,
                "entity_type_supported": supported,
                "implementation_status_supported": supported,
                "corrected_implementation_status": None,
                "reason": reason,
            }
        ]
    }


def test_no_product_evidence_uses_conservative_profile_and_question(tmp_path: Path) -> None:
    store, state = save_state(
        tmp_path,
        WorkflowStatus.REFERENCE_STYLE_ANALYZED,
        [reference_evidence()],
    )

    result = ProductUnderstandingAgent(state_store=store).understand_run(state.run_id)

    assert result.product_capabilities == []
    assert result.product_facts == []
    assert result.product_profile.product_positioning == "待确认"
    assert MISSING_PRODUCT_QUESTION in result.pending_human_questions
    assert result.workflow_status == WorkflowStatus.PRODUCT_UNDERSTOOD
    assert result.next_action == NextAction.DIAGNOSE_SOFTWARE_TYPE


def test_current_capability_with_valid_quote_is_accepted(tmp_path: Path) -> None:
    quote = "系统支持数据集管理和样本标注"
    _, result = _run(
        tmp_path,
        f"{quote}。",
        {"capabilities": [_candidate("数据集管理", CapabilityType.DATASET_MANAGEMENT, quote)]},
    )

    capability = result.product_capabilities[0]
    assert capability.name == "数据集管理"
    assert capability.validation_status == ValidationStatus.VALIDATED
    assert capability.implementation_status == ImplementationStatus.CURRENT
    assert capability.evidence_supports[0].evidence_id == "ev_product"
    assert "数据集管理" in result.product_profile.feature_list
    assert result.product_facts[0].supporting_quotes == [quote]


def test_product_understanding_generates_validation_trace_for_accepted_capability(
    tmp_path: Path,
) -> None:
    quote = "系统支持数据集管理和样本标注"
    _, result = _run(
        tmp_path,
        quote,
        {"capabilities": [_candidate("数据集管理", CapabilityType.DATASET_MANAGEMENT, quote)]},
    )

    trace = result.product_capabilities[0].validation_trace
    assert trace is not None
    assert trace.source_grounded is True
    assert trace.semantic_grounded is True
    assert trace.claim_hash
    assert trace.evidence_supports_hash


def test_capability_without_evidence_id_is_rejected(tmp_path: Path) -> None:
    quote = "系统支持数据集管理和样本标注"
    _, result = _run(
        tmp_path,
        quote,
        {
            "capabilities": [
                _candidate("数据集管理", CapabilityType.DATASET_MANAGEMENT, quote, evidence_ids=[])
            ]
        },
    )

    assert result.product_capabilities == []
    assert "数据集管理" not in result.product_profile.feature_list
    assert result.warnings


def test_capability_with_reference_style_evidence_is_rejected(tmp_path: Path) -> None:
    quote = "系统支持数据集管理和样本标注"
    store, state = save_state(
        tmp_path,
        WorkflowStatus.REFERENCE_STYLE_ANALYZED,
        [product_evidence(summary=quote), reference_evidence()],
    )
    provider = MockLLMProvider(
        json_response={
            "capabilities": [
                _candidate(
                    "参考秘密能力",
                    CapabilityType.OTHER,
                    "参考产品包含秘密模块",
                    evidence_ids=["ev_reference"],
                )
            ]
        }
    )

    result = ProductUnderstandingAgent(state_store=store, llm_provider=provider).understand_run(
        state.run_id
    )

    assert result.product_capabilities == []
    assert result.product_facts == []
    assert any("不是 product_evidence" in item for item in result.warnings)


def test_capability_with_quote_not_in_evidence_is_rejected(tmp_path: Path) -> None:
    _, result = _run(
        tmp_path,
        "系统支持数据集管理。",
        {
            "capabilities": [
                _candidate("秘密功能", CapabilityType.OTHER, "不存在的功能描述")
            ]
        },
    )

    assert result.product_capabilities == []
    assert result.product_profile.feature_list == []
    assert "证据不足：秘密功能" in result.product_profile.uncertain_features


def test_planned_ai_capability_does_not_enter_current_feature_list(tmp_path: Path) -> None:
    quote = "未来规划中将支持模型训练"
    _, result = _run(
        tmp_path,
        f"{quote}。",
        {
            "capabilities": [
                _candidate(
                    "模型训练",
                    CapabilityType.AI_TRAINING,
                    quote,
                    status=ImplementationStatus.PLANNED,
                )
            ]
        },
    )

    assert result.product_capabilities[0].implementation_status == ImplementationStatus.PLANNED
    assert "模型训练" not in result.product_profile.feature_list
    assert "模型训练" in result.product_profile.uncertain_features


def test_3d_model_import_is_not_ai_platform(tmp_path: Path) -> None:
    quote = "当前版本支持三维模型导入与查看"
    _, result = _run(
        tmp_path,
        f"{quote}。",
        {
            "capabilities": [
                _candidate("三维模型导入与查看", CapabilityType.THREE_D_MODEL_MANAGEMENT, quote)
            ]
        },
    )

    assert result.product_capabilities[0].capability_type == CapabilityType.THREE_D_MODEL_MANAGEMENT
    assert "三维模型" in result.product_profile.technical_keywords
    assert "AI 平台" not in result.product_profile.product_positioning


def test_simulation_result_import_is_not_data_platform_by_default(tmp_path: Path) -> None:
    quote = "系统支持仿真结果导入"
    _, result = _run(
        tmp_path,
        f"{quote}。",
        {
            "capabilities": [
                _candidate("仿真结果导入", CapabilityType.FILE_IMPORT_EXPORT, quote)
            ],
            "business_objects": [],
        },
    )

    assert "仿真结果导入" in result.product_profile.feature_list
    assert "数据管理" not in result.product_profile.product_positioning
    assert "导入" not in result.product_profile.business_objects


def test_no_keyword_only_support(tmp_path: Path) -> None:
    _, result = _run(
        tmp_path,
        "系统支持仿真结果导入。",
        {
            "capabilities": [
                _candidate("三维仿真秘密模块", CapabilityType.SIMULATION_MANAGEMENT, "仿真")
            ]
        },
    )

    assert result.product_capabilities == []
    assert result.product_profile.feature_list == []


def test_semantic_verifier_rejects_ai_training_from_3d_model_quote(tmp_path: Path) -> None:
    quote = "当前版本支持三维模型导入与查看"
    llm_data = {
        "capabilities": [_candidate("AI模型训练", CapabilityType.AI_TRAINING, quote)]
    }
    verifier_response = {
        "results": [
            {
                "candidate_index": 0,
                "supported": False,
                "name_supported": False,
                "capability_type_supported": False,
                "implementation_status_supported": True,
                "corrected_capability_type": None,
                "corrected_implementation_status": None,
                "reason": "quote 只支持三维模型导入与查看，不支持 AI 模型训练",
            }
        ]
    }

    _, result = _run(tmp_path, quote, llm_data, verifier_response=verifier_response)

    assert result.product_capabilities == []
    assert "AI模型训练" not in result.product_profile.feature_list
    assert "AI 平台" not in result.product_profile.product_positioning
    assert any("不支持 AI 模型训练" in warning for warning in result.warnings)


def test_semantic_verifier_accepts_true_3d_model_capability(tmp_path: Path) -> None:
    quote = "当前版本支持三维模型导入与查看"
    _, result = _run(
        tmp_path,
        quote,
        {
            "capabilities": [
                _candidate(
                    "三维模型导入与查看",
                    CapabilityType.THREE_D_MODEL_MANAGEMENT,
                    quote,
                )
            ]
        },
    )

    assert result.product_capabilities[0].name == "三维模型导入与查看"
    assert (
        result.product_capabilities[0].capability_type
        == CapabilityType.THREE_D_MODEL_MANAGEMENT
    )
    assert "AI 平台" not in result.product_profile.product_positioning
    assert "三维模型导入与查看" in result.product_profile.feature_list


def test_semantic_verifier_corrects_capability_type(tmp_path: Path) -> None:
    quote = "当前版本支持三维模型导入与查看"
    verifier_response = {
        "results": [
            {
                "candidate_index": 0,
                "supported": True,
                "name_supported": True,
                "capability_type_supported": False,
                "implementation_status_supported": True,
                "corrected_capability_type": CapabilityType.THREE_D_MODEL_MANAGEMENT.value,
                "corrected_implementation_status": None,
                "reason": "应修正为三维模型管理",
            }
        ]
    }

    _, result = _run(
        tmp_path,
        quote,
        {
            "capabilities": [
                _candidate("三维模型导入与查看", CapabilityType.AI_TRAINING, quote)
            ]
        },
        verifier_response=verifier_response,
    )

    assert (
        result.product_capabilities[0].capability_type
        == CapabilityType.THREE_D_MODEL_MANAGEMENT
    )
    assert "三维模型" in result.product_profile.technical_keywords
    assert "模型训练" not in result.product_profile.technical_keywords
    assert any("capability_type 已由 verifier 修正" in warning for warning in result.warnings)


def test_product_understanding_trace_hash_matches_final_corrected_type(
    tmp_path: Path,
) -> None:
    quote = "当前版本支持三维模型导入与查看"
    verifier_response = {
        "results": [
            {
                "candidate_index": 0,
                "supported": True,
                "name_supported": True,
                "capability_type_supported": False,
                "implementation_status_supported": True,
                "corrected_capability_type": CapabilityType.THREE_D_MODEL_MANAGEMENT.value,
                "corrected_implementation_status": None,
                "reason": "应修正为三维模型管理",
            }
        ]
    }
    _, result = _run(
        tmp_path,
        quote,
        {
            "capabilities": [
                _candidate("三维模型导入与查看", CapabilityType.AI_TRAINING, quote)
            ]
        },
        verifier_response=verifier_response,
    )

    capability = result.product_capabilities[0]
    assert capability.capability_type == CapabilityType.THREE_D_MODEL_MANAGEMENT
    validate_capability_trace(capability)


def test_semantic_verifier_corrects_planned_status(tmp_path: Path) -> None:
    quote = "未来规划中将支持模型训练"
    verifier_response = {
        "results": [
            {
                "candidate_index": 0,
                "supported": True,
                "name_supported": True,
                "capability_type_supported": True,
                "implementation_status_supported": False,
                "corrected_capability_type": None,
                "corrected_implementation_status": ImplementationStatus.PLANNED.value,
                "reason": "quote 表达的是规划能力",
            }
        ]
    }

    _, result = _run(
        tmp_path,
        quote,
        {"capabilities": [_candidate("模型训练", CapabilityType.AI_TRAINING, quote)]},
        verifier_response=verifier_response,
    )

    assert result.product_capabilities[0].implementation_status == ImplementationStatus.PLANNED
    assert "模型训练" not in result.product_profile.feature_list
    assert "模型训练" in result.product_profile.uncertain_features


def test_planning_quote_downgrades_current_even_if_verifier_misses_it(tmp_path: Path) -> None:
    quote = "Future roadmap will support model training"

    _, result = _run(
        tmp_path,
        quote,
        {"capabilities": [_candidate("Model training", CapabilityType.AI_TRAINING, quote)]},
    )

    assert result.product_capabilities[0].implementation_status == ImplementationStatus.PLANNED
    assert "Model training" not in result.product_profile.feature_list
    assert any("状态已降级为 planned" in warning for warning in result.warnings)


def test_product_understanding_trace_hash_matches_planning_downgrade(
    tmp_path: Path,
) -> None:
    quote = "未来规划中将支持模型训练"
    _, result = _run(
        tmp_path,
        quote,
        {"capabilities": [_candidate("模型训练", CapabilityType.AI_TRAINING, quote)]},
    )

    capability = result.product_capabilities[0]
    assert capability.implementation_status == ImplementationStatus.PLANNED
    validate_capability_trace(capability)


def test_verifier_missing_result_rejects_candidate(tmp_path: Path) -> None:
    quote = "当前版本支持三维模型导入与查看"

    _, result = _run(
        tmp_path,
        quote,
        {
            "capabilities": [
                _candidate(
                    "三维模型导入与查看",
                    CapabilityType.THREE_D_MODEL_MANAGEMENT,
                    quote,
                )
            ]
        },
        verifier_response={"results": []},
    )

    assert result.product_capabilities == []
    assert "证据不足：三维模型导入与查看" in result.product_profile.uncertain_features


def test_verifier_illegal_correction_rejects_candidate(tmp_path: Path) -> None:
    quote = "当前版本支持三维模型导入与查看"
    verifier_response = {
        "results": [
            {
                "candidate_index": 0,
                "supported": True,
                "name_supported": True,
                "capability_type_supported": False,
                "implementation_status_supported": True,
                "corrected_capability_type": "invented_capability_type",
                "corrected_implementation_status": None,
                "reason": "invalid correction",
            }
        ]
    }

    _, result = _run(
        tmp_path,
        quote,
        {
            "capabilities": [
                _candidate("三维模型导入与查看", CapabilityType.AI_TRAINING, quote)
            ]
        },
        verifier_response=verifier_response,
    )

    assert result.product_capabilities == []
    assert any("未提供合法修正值" in warning for warning in result.warnings)


def test_verifier_json_failure_fails_closed(tmp_path: Path) -> None:
    class FailingVerifierProvider(MockLLMProvider):
        def generate_json(
            self,
            messages: list[Any],
            temperature: float = 0.1,
            max_tokens: int | None = None,
        ) -> dict[str, Any]:
            raise ValueError("bad verifier json")

    quote = "当前版本支持三维模型导入与查看"
    llm_data = {
        "capabilities": [
            _candidate(
                "三维模型导入与查看",
                CapabilityType.THREE_D_MODEL_MANAGEMENT,
                quote,
            )
        ]
    }
    store, state = save_state(
        tmp_path,
        WorkflowStatus.REFERENCE_STYLE_ANALYZED,
        [product_evidence(summary=quote)],
    )
    agent = ProductUnderstandingAgent(
        state_store=store,
        llm_provider=MockLLMProvider(json_response=llm_data),
        grounding_verifier=ProductCapabilityGroundingVerifier(FailingVerifierProvider()),
    )

    result = agent.understand_run(state.run_id)

    assert result.product_capabilities == []
    assert any("verifier 解析失败" in warning for warning in result.warnings)


def test_grounded_business_object_page_user_and_workflow_are_accepted(tmp_path: Path) -> None:
    quote = "管理员在数据集页面执行样本审核流程"
    _, result = _run(
        tmp_path,
        quote,
        {
            "capabilities": [],
            "business_objects": [
                {
                    "name": "数据集",
                    "implementation_status": "current",
                    "supporting_evidence_ids": ["ev_product"],
                    "supporting_quotes": [quote],
                }
            ],
            "target_users": [
                {
                    "name": "管理员",
                    "implementation_status": "current",
                    "supporting_evidence_ids": ["ev_product"],
                    "supporting_quotes": [quote],
                }
            ],
            "pages": [
                {
                    "name": "数据集页面",
                    "implementation_status": "current",
                    "supporting_evidence_ids": ["ev_product"],
                    "supporting_quotes": [quote],
                }
            ],
            "workflows": [
                {
                    "name": "样本审核流程",
                    "implementation_status": "current",
                    "steps": ["进入页面", "执行审核"],
                    "supporting_evidence_ids": ["ev_product"],
                    "supporting_quotes": [quote],
                }
            ],
        },
    )

    assert result.product_profile.business_objects == ["数据集"]
    assert result.product_profile.target_users == ["管理员"]
    assert result.product_profile.page_list == ["数据集页面"]
    assert result.product_profile.core_workflows[0]["name"] == "样本审核流程"


def test_business_object_semantic_verifier_rejects_wrong_entity(tmp_path: Path) -> None:
    quote = "当前版本支持三维模型导入与查看"
    llm_data = {
        "capabilities": [
            _candidate(
                "三维模型导入与查看",
                CapabilityType.THREE_D_MODEL_MANAGEMENT,
                quote,
            )
        ],
        "business_objects": [_entity("AI训练任务", quote)],
    }

    _, result = _run(
        tmp_path,
        quote,
        llm_data,
        profile_entity_response=_entity_result(
            False,
            "quote 不支持 AI训练任务这个业务对象",
        ),
    )

    assert result.product_capabilities[0].name == "三维模型导入与查看"
    assert "AI训练任务" not in result.product_profile.business_objects
    assert "证据不足：AI训练任务" in result.product_profile.uncertain_features
    assert any("不支持 AI训练任务" in warning for warning in result.warnings)


def test_page_semantic_verifier_rejects_inferred_page(tmp_path: Path) -> None:
    quote = "系统支持数据集导入"

    _, result = _run(
        tmp_path,
        quote,
        {"capabilities": [], "pages": [_entity("数据集详情页", quote)]},
        profile_entity_response=_entity_result(False, "quote 不支持页面存在"),
    )

    assert "数据集详情页" not in result.product_profile.page_list


def test_workflow_semantic_verifier_rejects_inferred_workflow(tmp_path: Path) -> None:
    quote = "系统支持数据集导入"

    _, result = _run(
        tmp_path,
        quote,
        {
            "capabilities": [],
            "workflows": [_entity("数据集导入流程", quote, ["选择文件", "确认上传"])],
        },
        profile_entity_response=_entity_result(False, "单个功能点不支持完整流程"),
    )

    assert result.product_profile.core_workflows == []


def test_target_user_semantic_verifier_rejects_inferred_user(tmp_path: Path) -> None:
    quote = "系统支持数据集导入"

    _, result = _run(
        tmp_path,
        quote,
        {"capabilities": [], "target_users": [_entity("数据标注员", quote)]},
        profile_entity_response=_entity_result(False, "功能不能推断用户"),
    )

    assert "数据标注员" not in result.product_profile.target_users


def test_profile_entity_type_must_be_supported_even_if_verifier_marks_supported(
    tmp_path: Path,
) -> None:
    quote = "系统支持数据集导入"
    inconsistent_result = {
        "results": [
            {
                "entity_index": 0,
                "supported": True,
                "name_supported": True,
                "entity_type_supported": False,
                "reason": "quote 支持名称，但不支持它是页面",
            }
        ]
    }

    _, result = _run(
        tmp_path,
        quote,
        {"capabilities": [], "pages": [_entity("数据集导入", quote)]},
        profile_entity_response=inconsistent_result,
    )

    assert result.product_profile.page_list == []
    assert "证据不足：数据集导入" in result.product_profile.uncertain_features


def test_valid_business_object_is_accepted_after_semantic_verification(
    tmp_path: Path,
) -> None:
    quote = "系统管理数据集和样本"

    _, result = _run(
        tmp_path,
        quote,
        {"capabilities": [], "business_objects": [_entity("数据集", quote)]},
    )

    assert "数据集" in result.product_profile.business_objects


def test_valid_page_is_accepted_after_semantic_verification(tmp_path: Path) -> None:
    quote = "系统提供数据集详情页，用于查看样本列表"

    _, result = _run(
        tmp_path,
        quote,
        {"capabilities": [], "pages": [_entity("数据集详情页", "系统提供数据集详情页")]},
    )

    assert "数据集详情页" in result.product_profile.page_list


def test_planned_page_does_not_enter_current_page_list(tmp_path: Path) -> None:
    quote = "未来规划中将支持AI训练页面"
    verifier_response = {
        "results": [
            {
                "entity_index": 0,
                "supported": True,
                "name_supported": True,
                "entity_type_supported": True,
                "implementation_status_supported": False,
                "corrected_implementation_status": ImplementationStatus.PLANNED.value,
                "reason": "quote 表达的是未来规划页面",
            }
        ]
    }

    _, result = _run(
        tmp_path,
        quote,
        {"capabilities": [], "pages": [_entity("AI训练页面", quote)]},
        profile_entity_response=verifier_response,
    )

    assert "AI训练页面" not in result.product_profile.page_list
    assert "规划中：AI训练页面" in result.product_profile.uncertain_features
    assert any("implementation_status 已由 verifier 修正为 planned" in item for item in result.warnings)


def test_unknown_target_user_does_not_enter_target_users(tmp_path: Path) -> None:
    quote = "系统支持数据集导入"

    _, result = _run(
        tmp_path,
        quote,
        {
            "capabilities": [],
            "target_users": [
                _entity(
                    "数据标注员",
                    quote,
                    status=ImplementationStatus.UNKNOWN,
                )
            ],
        },
    )

    assert "数据标注员" not in result.product_profile.target_users
    assert "状态待确认：数据标注员" in result.product_profile.uncertain_features


def test_current_page_enters_page_list(tmp_path: Path) -> None:
    quote = "当前版本提供数据集详情页，用于查看样本列表"

    _, result = _run(
        tmp_path,
        quote,
        {"capabilities": [], "pages": [_entity("数据集详情页", "当前版本提供数据集详情页")]},
    )

    assert "数据集详情页" in result.product_profile.page_list


def test_planning_quote_downgrades_profile_entity_even_if_verifier_misses_it(
    tmp_path: Path,
) -> None:
    quote = "后续将支持审批流程"

    _, result = _run(
        tmp_path,
        quote,
        {
            "capabilities": [],
            "workflows": [_entity("审批流程", quote, ["提交", "审批"])],
        },
    )

    assert result.product_profile.core_workflows == []
    assert "规划中：审批流程" in result.product_profile.uncertain_features
    assert any("状态已降级为 planned" in warning for warning in result.warnings)


def test_planned_business_object_does_not_enter_business_objects(tmp_path: Path) -> None:
    quote = "未来规划中将支持数据交易市场"

    _, result = _run(
        tmp_path,
        quote,
        {
            "capabilities": [],
            "business_objects": [
                _entity(
                    "数据交易市场",
                    quote,
                    status=ImplementationStatus.PLANNED,
                )
            ],
        },
    )

    assert "数据交易市场" not in result.product_profile.business_objects
    assert "规划中：数据交易市场" in result.product_profile.uncertain_features


def test_missing_profile_entity_status_defaults_unknown(tmp_path: Path) -> None:
    quote = "系统管理数据集和样本"
    raw_entity = {
        "name": "数据集",
        "supporting_evidence_ids": ["ev_product"],
        "supporting_quotes": [quote],
    }
    verifier_response = {
        "results": [
            {
                "entity_index": 0,
                "supported": True,
                "name_supported": True,
                "entity_type_supported": True,
                "implementation_status_supported": True,
                "corrected_implementation_status": None,
                "reason": "status is unknown",
            }
        ]
    }

    _, result = _run(
        tmp_path,
        quote,
        {"capabilities": [], "business_objects": [raw_entity]},
        profile_entity_response=verifier_response,
    )

    assert result.product_profile.business_objects == []
    assert "状态待确认：数据集" in result.product_profile.uncertain_features


def test_profile_entity_status_verification_missing_rejects_entity(tmp_path: Path) -> None:
    quote = "当前版本提供数据集详情页"
    incomplete_result = {
        "results": [
            {
                "entity_index": 0,
                "supported": True,
                "name_supported": True,
                "entity_type_supported": True,
                "reason": "遗漏 implementation status 判断",
            }
        ]
    }

    _, result = _run(
        tmp_path,
        quote,
        {"capabilities": [], "pages": [_entity("数据集详情页", quote)]},
        profile_entity_response=incomplete_result,
    )

    assert result.product_profile.page_list == []
    assert "证据不足：数据集详情页" in result.product_profile.uncertain_features
    assert any("未提供合法修正值" in warning for warning in result.warnings)


def test_profile_entity_illegal_status_correction_rejects_entity(tmp_path: Path) -> None:
    quote = "未来规划中将支持AI训练页面"
    illegal_correction = {
        "results": [
            {
                "entity_index": 0,
                "supported": True,
                "name_supported": True,
                "entity_type_supported": True,
                "implementation_status_supported": False,
                "corrected_implementation_status": "future_someday",
                "reason": "invalid status correction",
            }
        ]
    }

    _, result = _run(
        tmp_path,
        quote,
        {"capabilities": [], "pages": [_entity("AI训练页面", quote)]},
        profile_entity_response=illegal_correction,
    )

    assert result.product_profile.page_list == []
    assert "证据不足：AI训练页面" in result.product_profile.uncertain_features
    assert any("未提供合法修正值" in warning for warning in result.warnings)


def test_profile_entity_without_source_grounding_is_rejected_before_verifier(
    tmp_path: Path,
) -> None:
    _, result = _run(
        tmp_path,
        "系统支持数据集导入",
        {
            "capabilities": [],
            "business_objects": [_entity("数据集", "不存在于证据中的引用短句")],
        },
    )

    assert result.product_profile.business_objects == []
    assert "证据不足：数据集" in result.product_profile.uncertain_features
    assert any("quote 无法在引用证据中找到" in warning for warning in result.warnings)


def test_profile_entity_verifier_missing_result_rejects_entity(tmp_path: Path) -> None:
    quote = "管理员在数据集页面执行样本审核流程"

    _, result = _run(
        tmp_path,
        quote,
        {
            "capabilities": [],
            "business_objects": [_entity("数据集", quote)],
            "target_users": [_entity("管理员", quote)],
            "pages": [_entity("数据集页面", quote)],
            "workflows": [_entity("样本审核流程", quote, ["进入页面", "执行审核"])],
        },
        profile_entity_response={"results": []},
    )

    assert result.product_profile.business_objects == []
    assert result.product_profile.target_users == []
    assert result.product_profile.page_list == []
    assert result.product_profile.core_workflows == []
    assert "证据不足：数据集" in result.product_profile.uncertain_features


def test_profile_entity_verifier_json_failure_fails_closed(tmp_path: Path) -> None:
    class FailingProfileEntityProvider(MockLLMProvider):
        def generate_json(
            self,
            messages: list[Any],
            temperature: float = 0.1,
            max_tokens: int | None = None,
        ) -> dict[str, Any]:
            raise ValueError("bad profile entity verifier json")

    quote = "系统管理数据集和样本"
    llm_data = {"capabilities": [], "business_objects": [_entity("数据集", quote)]}
    store, state = save_state(
        tmp_path,
        WorkflowStatus.REFERENCE_STYLE_ANALYZED,
        [product_evidence(summary=quote)],
    )
    agent = ProductUnderstandingAgent(
        state_store=store,
        llm_provider=MockLLMProvider(json_response=llm_data),
        profile_entity_verifier=ProductProfileEntityGroundingVerifier(
            FailingProfileEntityProvider()
        ),
    )

    result = agent.understand_run(state.run_id)

    assert result.product_profile.business_objects == []
    assert any("profile entity verifier 解析失败" in warning for warning in result.warnings)


def test_evidence_packets_read_chunk_text_and_exclude_reference_style(tmp_path: Path) -> None:
    product = product_evidence(summary="产品摘要")
    product.content_ref = "parsed/product/chunk_001.txt"
    reference = reference_evidence()
    store, state = save_state(
        tmp_path,
        WorkflowStatus.REFERENCE_STYLE_ANALYZED,
        [product, reference],
    )
    chunk = get_run_dir(state.run_id, tmp_path) / str(product.content_ref)
    chunk.parent.mkdir(parents=True, exist_ok=True)
    chunk.write_text("当前版本明确支持数据集管理能力", encoding="utf-8")
    agent = ProductUnderstandingAgent(
        state_store=store,
        llm_provider=MockLLMProvider(json_response={}),
    )

    packets = agent._build_evidence_packets(state)

    assert len(packets) == 1
    assert packets[0]["evidence_id"] == product.evidence_id
    assert packets[0]["text_excerpt"] == "当前版本明确支持数据集管理能力"
