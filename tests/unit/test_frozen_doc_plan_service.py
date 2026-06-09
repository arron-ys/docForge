from pathlib import Path

import pytest

from docforge_core.agents.capability_validation_trace import (
    build_capability_validation_trace,
)
from docforge_core.agents.frozen_doc_plan_service import FrozenDocPlanService
from docforge_core.agents.human_confirm_gate import DECISION_METADATA_KEY, HumanConfirmGate
from docforge_core.domain.enums import (
    AllowedUsage,
    CapabilityType,
    CorpusType,
    EvidenceType,
    ImplementationStatus,
    LockedBy,
    LockedStatus,
    NextAction,
    ValidationStatus,
    WorkflowStatus,
)
from docforge_core.domain.schemas import (
    DiagnosisResult,
    EvidenceSupport,
    ProductCapability,
    ProductFact,
    ProductProfile,
    TemplateStrategy,
)
from docforge_core.io.run_paths import get_run_dir

from .agent_helpers import capability, product_evidence, reference_evidence, save_state


def _confirmed_state(tmp_path: Path):
    store, state = save_state(
        tmp_path,
        WorkflowStatus.TEMPLATE_RECOMMENDED,
        [product_evidence(), reference_evidence()],
    )
    state.diagnosis_result = DiagnosisResult(
        primary_type="Web/SaaS 平台",
        enhancement_tags=["数据平台"],
    )
    state.template_strategy = TemplateStrategy(
        base_template_id="TEMPLATE_WEB",
        base_template_name="Web 模板",
        enhancement_pack_ids=["PACK_DATA_PLATFORM"],
        recommended_chapters=["引言", "核心功能说明"],
    )
    state.product_capabilities = [
        capability("cap_current", CapabilityType.DATASET_MANAGEMENT, name="数据集管理"),
        capability(
            "cap_planned",
            CapabilityType.AI_TRAINING,
            ImplementationStatus.PLANNED,
            name="模型训练",
        ),
        capability(
            "cap_unknown",
            CapabilityType.OTHER,
            ImplementationStatus.UNKNOWN,
            name="待确认能力",
        ),
    ]
    state.product_profile = ProductProfile(uncertain_features=["证据不足：秘密功能"])
    store.save_state(state)
    gate = HumanConfirmGate(store)
    prepared = gate.prepare_confirmation(state.run_id)
    decision = gate.build_default_decision(prepared)
    gate.confirm_template_strategy(state.run_id, decision)
    return store, state.run_id


def _tamper_decision(store, run_id: str, **updates) -> None:
    state = store.load_state(run_id)
    decision = state.human_confirmations[-1].metadata[DECISION_METADATA_KEY]
    decision.update(updates)
    store.save_state(state)


def _refresh_capability_trace(capability: ProductCapability) -> None:
    capability.validation_trace = build_capability_validation_trace(
        capability,
        {
            "supported": True,
            "name_supported": True,
            "capability_type_supported": True,
            "implementation_status_supported": True,
            "reason": "测试重新签发凭证以隔离冻结边界后续校验",
        },
    )


def test_freeze_requires_user_confirmed(tmp_path: Path) -> None:
    store, state = save_state(tmp_path, WorkflowStatus.TEMPLATE_RECOMMENDED)
    with pytest.raises(ValueError, match="USER_CONFIRMED"):
        FrozenDocPlanService(store).freeze_confirmed_plan(state.run_id)


def test_freeze_requires_confirmed_confirmation(tmp_path: Path) -> None:
    store, state = save_state(tmp_path, WorkflowStatus.USER_CONFIRMED)
    state.template_strategy = TemplateStrategy(
        base_template_id="T", base_template_name="模板", recommended_chapters=["引言"]
    )
    state.diagnosis_result = DiagnosisResult(primary_type="通用软件系统")
    store.save_state(state)
    with pytest.raises(ValueError, match="已确认"):
        FrozenDocPlanService(store).freeze_confirmed_plan(state.run_id)


def test_freeze_requires_confirmation_decision(tmp_path: Path) -> None:
    store, run_id = _confirmed_state(tmp_path)
    state = store.load_state(run_id)
    state.human_confirmations[-1].metadata.clear()
    store.save_state(state)

    with pytest.raises(ValueError, match="decision"):
        FrozenDocPlanService(store).freeze_confirmed_plan(run_id)


def test_freeze_rejects_empty_selected_top_level_chapters(tmp_path: Path) -> None:
    store, run_id = _confirmed_state(tmp_path)
    _tamper_decision(store, run_id, selected_top_level_chapters=[])

    with pytest.raises(ValueError, match="selected_top_level_chapters"):
        FrozenDocPlanService(store).freeze_confirmed_plan(run_id)


def test_freeze_rejects_tampered_base_template_id(tmp_path: Path) -> None:
    store, run_id = _confirmed_state(tmp_path)
    _tamper_decision(store, run_id, selected_base_template_id="EVIL_TEMPLATE")

    with pytest.raises(ValueError, match="selected_base_template_id"):
        FrozenDocPlanService(store).freeze_confirmed_plan(run_id)


def test_freeze_rejects_tampered_base_template_name(tmp_path: Path) -> None:
    store, run_id = _confirmed_state(tmp_path)
    _tamper_decision(store, run_id, selected_base_template_name="恶意模板")

    with pytest.raises(ValueError, match="selected_base_template_name"):
        FrozenDocPlanService(store).freeze_confirmed_plan(run_id)


def test_freeze_rejects_unknown_selected_top_level_chapter(tmp_path: Path) -> None:
    store, run_id = _confirmed_state(tmp_path)
    _tamper_decision(store, run_id, selected_top_level_chapters=["引言", "未知章节"])

    with pytest.raises(ValueError, match="未知章节"):
        FrozenDocPlanService(store).freeze_confirmed_plan(run_id)


def test_freeze_rejects_unknown_acknowledged_risk_chapter(tmp_path: Path) -> None:
    store, run_id = _confirmed_state(tmp_path)
    _tamper_decision(
        store,
        run_id,
        acknowledged_risk_chapters=["未知风险章节"],
        risk_acknowledged=True,
    )

    with pytest.raises(ValueError, match="未知风险章节"):
        FrozenDocPlanService(store).freeze_confirmed_plan(run_id)


def test_freeze_rejects_risk_chapter_selected_but_not_acknowledged_listed(
    tmp_path: Path,
) -> None:
    risk_chapter = "AI 能力当前版本状态待确认"
    store, run_id = _confirmed_state(tmp_path)
    state = store.load_state(run_id)
    assert state.template_strategy is not None
    state.template_strategy.risk_chapters = [risk_chapter]
    state.human_confirmations[-1].metadata[DECISION_METADATA_KEY].update(
        {
            "selected_top_level_chapters": ["引言", risk_chapter],
            "risk_acknowledged": True,
            "acknowledged_risk_chapters": [],
        }
    )
    store.save_state(state)

    with pytest.raises(ValueError, match="acknowledged_risk_chapters"):
        FrozenDocPlanService(store).freeze_confirmed_plan(run_id)


def test_freeze_builds_locked_evidence_grounded_contract(tmp_path: Path) -> None:
    store, run_id = _confirmed_state(tmp_path)

    result = FrozenDocPlanService(store).freeze_confirmed_plan(run_id)

    plan = result.frozen_doc_plan
    assert plan is not None
    assert result.workflow_status == WorkflowStatus.PLAN_FROZEN
    assert result.next_action == NextAction.CREATE_OUTLINE
    assert plan.locked_status == LockedStatus.LOCKED
    assert plan.locked_by == LockedBy.HUMAN
    assert plan.chapter_policy["locked_top_level_chapters"] == ["引言", "核心功能说明"]
    assert plan.chapter_policy["can_outline_change_level_1_sections"] is False
    assert plan.feature_policy["allowed_current_feature_names"] == ["数据集管理"]
    assert "模型训练" in plan.feature_policy["forbidden_as_current_feature_names"]
    assert "待确认能力" in plan.feature_policy["forbidden_as_current_feature_names"]
    assert "证据不足：秘密功能" in plan.feature_policy["forbidden_as_current_feature_names"]
    assert plan.evidence_policy["factual_evidence_filter"] == {
        "corpus_type": CorpusType.PRODUCT_EVIDENCE.value,
        "allowed_usage": AllowedUsage.FACTUAL_EVIDENCE.value,
    }
    assert plan.evidence_policy["style_reference_filter"] == {
        "corpus_type": CorpusType.REFERENCE_STYLE.value,
        "allowed_usage": AllowedUsage.STYLE_ONLY.value,
    }
    assert all(
        item["corpus_type"] == CorpusType.PRODUCT_EVIDENCE.value
        for item in plan.evidence_policy["evidence_trace"]
    )
    assert plan.downstream_permissions["outline_agent_can_change_top_level_chapters"] is False
    assert result.outline is None
    assert result.draft_versions == []


def test_frozen_doc_plan_excludes_screenshot_from_allowed_product_evidence_ids(
    tmp_path: Path,
) -> None:
    store, run_id = _confirmed_state(tmp_path)
    state = store.load_state(run_id)
    state.evidence_map.append(
        product_evidence(
            evidence_id="ev_screenshot",
            source_id="screen_source",
            evidence_type=EvidenceType.PRODUCT_SCREENSHOT,
            summary="产品截图已登记，视觉解析未执行。",
        )
    )
    store.save_state(state)

    result = FrozenDocPlanService(store).freeze_confirmed_plan(run_id)

    assert result.frozen_doc_plan is not None
    policy = result.frozen_doc_plan.evidence_policy
    screenshot_policy = result.frozen_doc_plan.screenshot_policy
    assert "ev_product" in policy["allowed_product_evidence_ids"]
    assert "ev_screenshot" not in policy["allowed_product_evidence_ids"]
    assert "ev_screenshot" in screenshot_policy["screenshot_evidence_ids"]


def test_frozen_doc_plan_screenshot_policy_never_allows_strong_fact_evidence(
    tmp_path: Path,
) -> None:
    store, run_id = _confirmed_state(tmp_path)
    state = store.load_state(run_id)
    state.evidence_map.append(
        product_evidence(
            evidence_id="ev_screenshot",
            source_id="screen_source",
            evidence_type=EvidenceType.PRODUCT_SCREENSHOT,
        )
    )
    store.save_state(state)

    result = FrozenDocPlanService(store).freeze_confirmed_plan(run_id)

    assert result.frozen_doc_plan is not None
    screenshot_policy = result.frozen_doc_plan.screenshot_policy
    assert screenshot_policy["screenshot_evidence_ids"] == ["ev_screenshot"]
    assert screenshot_policy["visual_parse_status"] == "not_performed"
    assert screenshot_policy["can_use_screenshot_as_strong_evidence"] is False
    assert screenshot_policy["can_use_screenshot_as_product_fact"] is False
    assert screenshot_policy["screenshot_usage"] == "figure_placeholder_only"
    assert screenshot_policy["screenshot_binding_status"] == "not_performed"


def test_freeze_keeps_validated_current_product_fact_with_product_evidence(
    tmp_path: Path,
) -> None:
    store, run_id = _confirmed_state(tmp_path)
    state = store.load_state(run_id)
    state.product_facts = [
        ProductFact(
            fact_id="fact_cap_current",
            content="数据集管理",
            source_ids=["product_source"],
            supporting_evidence_ids=["ev_product"],
            supporting_quotes=["当前版本明确支持该产品能力"],
            capability_type=CapabilityType.DATASET_MANAGEMENT,
            implementation_status=ImplementationStatus.CURRENT,
            validation_status=ValidationStatus.VALIDATED,
        )
    ]
    store.save_state(state)

    result = FrozenDocPlanService(store).freeze_confirmed_plan(run_id)

    assert result.frozen_doc_plan is not None
    assert result.frozen_doc_plan.feature_policy["current_facts"][0]["content"] == (
        "数据集管理"
    )


def test_freeze_rejects_reference_style_as_current_capability_evidence(tmp_path: Path) -> None:
    store, run_id = _confirmed_state(tmp_path)
    state = store.load_state(run_id)
    state.product_capabilities = [
        ProductCapability(
            capability_id="cap_bad",
            name="参考污染能力",
            capability_type=CapabilityType.OTHER,
            implementation_status=ImplementationStatus.CURRENT,
            validation_status=ValidationStatus.VALIDATED,
            confidence=0.9,
            evidence_supports=[
                EvidenceSupport(
                    evidence_id="ev_reference",
                    source_id="reference_source",
                    quote="参考产品包含秘密模块",
                )
            ],
        )
    ]
    _refresh_capability_trace(state.product_capabilities[0])
    store.save_state(state)

    with pytest.raises(ValueError, match="product_evidence"):
        FrozenDocPlanService(store).freeze_confirmed_plan(run_id)


def test_freeze_rejects_current_capability_without_evidence_supports(
    tmp_path: Path,
) -> None:
    store, run_id = _confirmed_state(tmp_path)
    state = store.load_state(run_id)
    state.product_capabilities = [
        ProductCapability.model_construct(
            capability_id="cap_bad",
            name="无证据当前能力",
            capability_type=CapabilityType.OTHER,
            implementation_status=ImplementationStatus.CURRENT,
            validation_status=ValidationStatus.VALIDATED,
            confidence=0.9,
            evidence_supports=[],
        )
    ]
    store.save_state(state)

    with pytest.raises(ValueError, match="evidence_supports"):
        FrozenDocPlanService(store).freeze_confirmed_plan(run_id)


def test_frozen_doc_plan_rejects_current_capability_supported_by_screenshot(
    tmp_path: Path,
) -> None:
    store, run_id = _confirmed_state(tmp_path)
    state = store.load_state(run_id)
    state.evidence_map.append(
        product_evidence(
            evidence_id="ev_screenshot",
            source_id="screen_source",
            evidence_type=EvidenceType.PRODUCT_SCREENSHOT,
            summary="截图摘要不应成为正文事实证据",
        )
    )
    capability = state.product_capabilities[0]
    capability.evidence_supports[0].evidence_id = "ev_screenshot"
    capability.evidence_supports[0].source_id = "screen_source"
    capability.evidence_supports[0].quote = "截图摘要不应成为正文事实证据"
    _refresh_capability_trace(capability)
    store.save_state(state)

    with pytest.raises(ValueError, match="截图 evidence"):
        FrozenDocPlanService(store).freeze_confirmed_plan(run_id)


def test_freeze_rejects_capability_support_source_id_mismatch(tmp_path: Path) -> None:
    store, run_id = _confirmed_state(tmp_path)
    state = store.load_state(run_id)
    state.product_capabilities[0].evidence_supports[0].source_id = "reference_source"
    _refresh_capability_trace(state.product_capabilities[0])
    store.save_state(state)

    with pytest.raises(ValueError, match="source_id|evidence.source_id"):
        FrozenDocPlanService(store).freeze_confirmed_plan(run_id)


def test_freeze_rejects_capability_support_empty_source_id(tmp_path: Path) -> None:
    store, run_id = _confirmed_state(tmp_path)
    state = store.load_state(run_id)
    state.product_capabilities[0].evidence_supports[0].source_id = ""
    _refresh_capability_trace(state.product_capabilities[0])
    store.save_state(state)

    with pytest.raises(ValueError, match="source_id"):
        FrozenDocPlanService(store).freeze_confirmed_plan(run_id)


def test_freeze_rejects_capability_support_reference_source_id(tmp_path: Path) -> None:
    store, run_id = _confirmed_state(tmp_path)
    state = store.load_state(run_id)
    reference_item = next(
        item for item in state.evidence_map if item.corpus_type == CorpusType.REFERENCE_STYLE
    )
    reference_item.source_id = "product_source"
    store.save_state(state)

    with pytest.raises(ValueError, match="reference source"):
        FrozenDocPlanService(store).freeze_confirmed_plan(run_id)


def test_freeze_rejects_capability_support_empty_quote(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store, run_id = _confirmed_state(tmp_path)
    state = store.load_state(run_id)
    state.product_capabilities[0].evidence_supports[0].quote = ""
    _refresh_capability_trace(state.product_capabilities[0])
    monkeypatch.setattr(store, "load_state", lambda _: state)

    with pytest.raises(ValueError, match="quote"):
        FrozenDocPlanService(store).freeze_confirmed_plan(run_id)


def test_freeze_keeps_clean_current_capability_support(tmp_path: Path) -> None:
    store, run_id = _confirmed_state(tmp_path)

    result = FrozenDocPlanService(store).freeze_confirmed_plan(run_id)

    assert result.frozen_doc_plan is not None
    current_support = result.frozen_doc_plan.feature_policy["current_capabilities"][0][
        "evidence_supports"
    ][0]
    trace = result.frozen_doc_plan.evidence_policy["evidence_trace"][0]
    assert current_support["source_id"] == "product_source"
    assert trace["source_id"] == "product_source"


def test_freeze_rejects_current_capability_without_validation_trace(
    tmp_path: Path,
) -> None:
    store, run_id = _confirmed_state(tmp_path)
    state = store.load_state(run_id)
    state.product_capabilities[0].validation_trace = None
    store.save_state(state)

    with pytest.raises(ValueError, match="validation_trace"):
        FrozenDocPlanService(store).freeze_confirmed_plan(run_id)


def test_freeze_rejects_current_capability_with_tampered_name_after_validation(
    tmp_path: Path,
) -> None:
    store, run_id = _confirmed_state(tmp_path)
    state = store.load_state(run_id)
    state.product_capabilities[0].name = "AI模型训练"
    store.save_state(state)

    with pytest.raises(ValueError, match="claim_hash|validation_trace"):
        FrozenDocPlanService(store).freeze_confirmed_plan(run_id)


def test_freeze_rejects_current_capability_with_tampered_capability_type_after_validation(
    tmp_path: Path,
) -> None:
    store, run_id = _confirmed_state(tmp_path)
    state = store.load_state(run_id)
    state.product_capabilities[0].capability_type = CapabilityType.AI_TRAINING
    store.save_state(state)

    with pytest.raises(ValueError, match="claim_hash|validation_trace"):
        FrozenDocPlanService(store).freeze_confirmed_plan(run_id)


def test_freeze_rejects_current_capability_with_tampered_implementation_status_after_validation(
    tmp_path: Path,
) -> None:
    store, run_id = _confirmed_state(tmp_path)
    state = store.load_state(run_id)
    planned = next(
        item
        for item in state.product_capabilities
        if item.implementation_status == ImplementationStatus.PLANNED
    )
    planned.implementation_status = ImplementationStatus.CURRENT
    store.save_state(state)

    with pytest.raises(ValueError, match="claim_hash|validation_trace"):
        FrozenDocPlanService(store).freeze_confirmed_plan(run_id)


def test_freeze_rejects_current_capability_with_tampered_evidence_support_quote_after_validation(
    tmp_path: Path,
) -> None:
    store, run_id = _confirmed_state(tmp_path)
    state = store.load_state(run_id)
    state.product_capabilities[0].evidence_supports[0].quote = (
        "数据集导入页面支持权限管理"
    )
    store.save_state(state)

    with pytest.raises(ValueError, match="evidence_supports_hash|validation_trace"):
        FrozenDocPlanService(store).freeze_confirmed_plan(run_id)


def test_freeze_accepts_current_capability_with_valid_validation_trace(
    tmp_path: Path,
) -> None:
    store, run_id = _confirmed_state(tmp_path)

    result = FrozenDocPlanService(store).freeze_confirmed_plan(run_id)

    assert result.workflow_status == WorkflowStatus.PLAN_FROZEN
    assert result.frozen_doc_plan is not None
    trace = result.frozen_doc_plan.feature_policy["current_capabilities"][0][
        "validation_trace"
    ]
    assert trace["source_grounded"] is True
    assert trace["semantic_grounded"] is True


def test_freeze_rejects_validated_ai_training_with_3d_model_quote_without_matching_trace(
    tmp_path: Path,
) -> None:
    store, run_id = _confirmed_state(tmp_path)
    state = store.load_state(run_id)
    product_item = next(
        item for item in state.evidence_map if item.evidence_id == "ev_product"
    )
    product_item.summary = "当前版本支持三维模型导入与查看"
    capability = state.product_capabilities[0]
    capability.evidence_supports[0].quote = "当前版本支持三维模型导入与查看"
    _refresh_capability_trace(capability)
    capability.name = "AI模型训练"
    capability.capability_type = CapabilityType.AI_TRAINING
    store.save_state(state)

    with pytest.raises(ValueError, match="claim_hash|validation_trace"):
        FrozenDocPlanService(store).freeze_confirmed_plan(run_id)


def test_freeze_rejects_capability_support_quote_not_in_evidence(tmp_path: Path) -> None:
    store, run_id = _confirmed_state(tmp_path)
    state = store.load_state(run_id)
    state.product_capabilities[0].evidence_supports[0].quote = "完全不存在的引用文本"
    _refresh_capability_trace(state.product_capabilities[0])
    store.save_state(state)

    with pytest.raises(ValueError, match="quote|EvidenceSupport"):
        FrozenDocPlanService(store).freeze_confirmed_plan(run_id)


def test_freeze_accepts_capability_support_quote_in_evidence_summary(
    tmp_path: Path,
) -> None:
    store, run_id = _confirmed_state(tmp_path)
    state = store.load_state(run_id)
    product_item = next(
        item for item in state.evidence_map if item.evidence_id == "ev_product"
    )
    product_item.summary = "当前版本支持数据集管理"
    state.product_capabilities[0].evidence_supports[0].quote = "当前版本支持数据集管理"
    _refresh_capability_trace(state.product_capabilities[0])
    store.save_state(state)

    result = FrozenDocPlanService(store).freeze_confirmed_plan(run_id)

    assert result.workflow_status == WorkflowStatus.PLAN_FROZEN


def test_freeze_accepts_capability_support_quote_in_content_ref(tmp_path: Path) -> None:
    store, run_id = _confirmed_state(tmp_path)
    state = store.load_state(run_id)
    product_item = next(
        item for item in state.evidence_map if item.evidence_id == "ev_product"
    )
    product_item.summary = "无关摘要"
    product_item.content_ref = "parsed/chunk_001.txt"
    state.product_capabilities[0].evidence_supports[0].quote = "当前版本支持数据集管理"
    _refresh_capability_trace(state.product_capabilities[0])
    chunk = get_run_dir(run_id, tmp_path) / product_item.content_ref
    chunk.parent.mkdir(parents=True, exist_ok=True)
    chunk.write_text("当前版本支持数据集管理", encoding="utf-8")
    store.save_state(state)

    result = FrozenDocPlanService(store).freeze_confirmed_plan(run_id)

    assert result.workflow_status == WorkflowStatus.PLAN_FROZEN


def test_freeze_rejects_capability_support_quote_path_traversal_content_ref(
    tmp_path: Path,
) -> None:
    store, run_id = _confirmed_state(tmp_path)
    state = store.load_state(run_id)
    product_item = next(
        item for item in state.evidence_map if item.evidence_id == "ev_product"
    )
    product_item.summary = "无关摘要"
    product_item.content_ref = "../../evil.txt"
    state.product_capabilities[0].evidence_supports[0].quote = "当前版本支持数据集管理"
    _refresh_capability_trace(state.product_capabilities[0])
    (tmp_path / "evil.txt").write_text("当前版本支持数据集管理", encoding="utf-8")
    store.save_state(state)

    with pytest.raises(ValueError, match="quote|EvidenceSupport"):
        FrozenDocPlanService(store).freeze_confirmed_plan(run_id)


def test_freeze_rejects_capability_support_too_short_keyword_quote(
    tmp_path: Path,
) -> None:
    store, run_id = _confirmed_state(tmp_path)
    state = store.load_state(run_id)
    product_item = next(
        item for item in state.evidence_map if item.evidence_id == "ev_product"
    )
    product_item.summary = "当前版本支持三维模型导入与查看"
    state.product_capabilities[0].evidence_supports[0].quote = "模型"
    _refresh_capability_trace(state.product_capabilities[0])
    store.save_state(state)

    with pytest.raises(ValueError, match="quote|EvidenceSupport"):
        FrozenDocPlanService(store).freeze_confirmed_plan(run_id)


def test_frozen_plan_current_capabilities_do_not_include_raw_description_or_reasoning(
    tmp_path: Path,
) -> None:
    store, run_id = _confirmed_state(tmp_path)
    state = store.load_state(run_id)
    state.product_capabilities[0].description = "无证据描述：支持AI模型训练"
    state.product_capabilities[0].reasoning = "无证据推理"
    store.save_state(state)

    result = FrozenDocPlanService(store).freeze_confirmed_plan(run_id)

    assert result.frozen_doc_plan is not None
    frozen_capability = result.frozen_doc_plan.feature_policy["current_capabilities"][0]
    assert "description" not in frozen_capability
    assert "reasoning" not in frozen_capability


def test_freeze_rejects_current_product_fact_with_reference_style_evidence(
    tmp_path: Path,
) -> None:
    store, run_id = _confirmed_state(tmp_path)
    state = store.load_state(run_id)
    state.product_facts = [
        ProductFact(
            content="参考资料中的秘密功能",
            source_ids=["reference_source"],
            supporting_evidence_ids=["ev_reference"],
            implementation_status=ImplementationStatus.CURRENT,
            validation_status=ValidationStatus.VALIDATED,
        )
    ]
    store.save_state(state)

    with pytest.raises(ValueError, match="product_evidence|reference_style"):
        FrozenDocPlanService(store).freeze_confirmed_plan(run_id)


def test_frozen_doc_plan_rejects_product_fact_supported_by_screenshot(
    tmp_path: Path,
) -> None:
    store, run_id = _confirmed_state(tmp_path)
    state = store.load_state(run_id)
    state.evidence_map.append(
        product_evidence(
            evidence_id="ev_screenshot",
            source_id="screen_source",
            evidence_type=EvidenceType.PRODUCT_SCREENSHOT,
            summary="截图摘要不应成为正文事实证据",
        )
    )
    state.product_facts = [
        ProductFact(
            fact_id="fact_cap_current",
            content="数据集管理",
            source_ids=["screen_source"],
            supporting_evidence_ids=["ev_screenshot"],
            supporting_quotes=["截图摘要不应成为正文事实证据"],
            capability_type=CapabilityType.DATASET_MANAGEMENT,
            implementation_status=ImplementationStatus.CURRENT,
            validation_status=ValidationStatus.VALIDATED,
        )
    ]
    store.save_state(state)

    with pytest.raises(ValueError, match="截图 evidence"):
        FrozenDocPlanService(store).freeze_confirmed_plan(run_id)


def test_freeze_rejects_current_product_fact_without_supporting_evidence(
    tmp_path: Path,
) -> None:
    store, run_id = _confirmed_state(tmp_path)
    state = store.load_state(run_id)
    state.product_facts = [
        ProductFact(
            content="无证据当前事实",
            implementation_status=ImplementationStatus.CURRENT,
            validation_status=ValidationStatus.VALIDATED,
        )
    ]
    store.save_state(state)

    with pytest.raises(ValueError, match="supporting_evidence_ids"):
        FrozenDocPlanService(store).freeze_confirmed_plan(run_id)


def test_freeze_rejects_current_product_fact_with_missing_evidence_id(
    tmp_path: Path,
) -> None:
    store, run_id = _confirmed_state(tmp_path)
    state = store.load_state(run_id)
    state.product_facts = [
        ProductFact(
            content="缺失证据当前事实",
            supporting_evidence_ids=["ev_missing"],
            implementation_status=ImplementationStatus.CURRENT,
            validation_status=ValidationStatus.VALIDATED,
        )
    ]
    store.save_state(state)

    with pytest.raises(ValueError, match="不存在的 evidence"):
        FrozenDocPlanService(store).freeze_confirmed_plan(run_id)


def test_freeze_rejects_current_product_fact_with_reference_source_id(
    tmp_path: Path,
) -> None:
    store, run_id = _confirmed_state(tmp_path)
    state = store.load_state(run_id)
    state.product_facts = [
        ProductFact(
            content="证据合法但来源污染",
            source_ids=["reference_source"],
            supporting_evidence_ids=["ev_product"],
            implementation_status=ImplementationStatus.CURRENT,
            validation_status=ValidationStatus.VALIDATED,
        )
    ]
    store.save_state(state)

    with pytest.raises(ValueError, match="reference_style source_id"):
        FrozenDocPlanService(store).freeze_confirmed_plan(run_id)


def test_freeze_rejects_current_product_fact_not_linked_to_current_capability(
    tmp_path: Path,
) -> None:
    store, run_id = _confirmed_state(tmp_path)
    state = store.load_state(run_id)
    state.product_facts = [
        ProductFact(
            fact_id="fact_fake",
            content="完全不存在的秘密功能",
            source_ids=["product_source"],
            supporting_evidence_ids=["ev_product"],
            supporting_quotes=["当前版本明确支持该产品能力"],
            implementation_status=ImplementationStatus.CURRENT,
            validation_status=ValidationStatus.VALIDATED,
        )
    ]
    store.save_state(state)

    with pytest.raises(ValueError, match="绑定"):
        FrozenDocPlanService(store).freeze_confirmed_plan(run_id)


def test_freeze_rejects_current_product_fact_content_mismatch_with_capability(
    tmp_path: Path,
) -> None:
    store, run_id = _confirmed_state(tmp_path)
    state = store.load_state(run_id)
    state.product_facts = [
        ProductFact(
            fact_id="fact_cap_current",
            content="秘密功能",
            source_ids=["product_source"],
            supporting_evidence_ids=["ev_product"],
            supporting_quotes=["当前版本明确支持该产品能力"],
            capability_type=CapabilityType.DATASET_MANAGEMENT,
            implementation_status=ImplementationStatus.CURRENT,
            validation_status=ValidationStatus.VALIDATED,
        )
    ]
    store.save_state(state)

    with pytest.raises(ValueError, match="content"):
        FrozenDocPlanService(store).freeze_confirmed_plan(run_id)


def test_freeze_rejects_current_product_fact_quote_not_in_capability_supports(
    tmp_path: Path,
) -> None:
    store, run_id = _confirmed_state(tmp_path)
    state = store.load_state(run_id)
    state.product_facts = [
        ProductFact(
            fact_id="fact_cap_current",
            content="数据集管理",
            source_ids=["product_source"],
            supporting_evidence_ids=["ev_product"],
            supporting_quotes=["完全不存在的引用文本"],
            capability_type=CapabilityType.DATASET_MANAGEMENT,
            implementation_status=ImplementationStatus.CURRENT,
            validation_status=ValidationStatus.VALIDATED,
        )
    ]
    store.save_state(state)

    with pytest.raises(ValueError, match="supporting_quotes"):
        FrozenDocPlanService(store).freeze_confirmed_plan(run_id)


def test_freeze_accepts_current_product_fact_derived_from_current_capability(
    tmp_path: Path,
) -> None:
    store, run_id = _confirmed_state(tmp_path)
    state = store.load_state(run_id)
    state.product_facts = [
        ProductFact(
            fact_id="fact_cap_current",
            content="数据集管理",
            source_ids=["product_source"],
            supporting_evidence_ids=["ev_product"],
            supporting_quotes=["当前版本明确支持该产品能力"],
            capability_type=CapabilityType.DATASET_MANAGEMENT,
            implementation_status=ImplementationStatus.CURRENT,
            validation_status=ValidationStatus.VALIDATED,
            reasoning="不应进入冻结计划的自由推理",
        )
    ]
    store.save_state(state)

    result = FrozenDocPlanService(store).freeze_confirmed_plan(run_id)

    assert result.frozen_doc_plan is not None
    frozen_fact = result.frozen_doc_plan.feature_policy["current_facts"][0]
    assert frozen_fact["content"] == "数据集管理"
    assert "reasoning" not in frozen_fact


def test_freeze_rejects_forbidden_feature_name_as_top_level_chapter(
    tmp_path: Path,
) -> None:
    store, run_id = _confirmed_state(tmp_path)
    state = store.load_state(run_id)
    assert state.template_strategy is not None
    state.template_strategy.recommended_chapters.append("模型训练")
    state.human_confirmations[-1].metadata[DECISION_METADATA_KEY][
        "selected_top_level_chapters"
    ] = ["引言", "模型训练"]
    store.save_state(state)

    with pytest.raises(ValueError, match="一级目录不得包含"):
        FrozenDocPlanService(store).freeze_confirmed_plan(run_id)


def test_freeze_rejects_uncertain_feature_as_top_level_chapter(
    tmp_path: Path,
) -> None:
    store, run_id = _confirmed_state(tmp_path)
    state = store.load_state(run_id)
    assert state.template_strategy is not None
    state.template_strategy.recommended_chapters.append("证据不足：秘密功能")
    state.human_confirmations[-1].metadata[DECISION_METADATA_KEY][
        "selected_top_level_chapters"
    ] = ["引言", "证据不足：秘密功能"]
    store.save_state(state)

    with pytest.raises(ValueError, match="一级目录不得包含"):
        FrozenDocPlanService(store).freeze_confirmed_plan(run_id)


def test_freeze_rejects_forbidden_feature_variant_as_top_level_chapter(
    tmp_path: Path,
) -> None:
    store, run_id = _confirmed_state(tmp_path)
    state = store.load_state(run_id)
    assert state.template_strategy is not None
    state.template_strategy.recommended_chapters.append("模型训练功能")
    state.human_confirmations[-1].metadata[DECISION_METADATA_KEY][
        "selected_top_level_chapters"
    ] = ["引言", "模型训练功能"]
    store.save_state(state)

    with pytest.raises(ValueError, match="一级目录不得包含"):
        FrozenDocPlanService(store).freeze_confirmed_plan(run_id)


def test_freeze_rejects_uncertain_feature_variant_as_top_level_chapter(
    tmp_path: Path,
) -> None:
    store, run_id = _confirmed_state(tmp_path)
    state = store.load_state(run_id)
    assert state.template_strategy is not None
    state.template_strategy.recommended_chapters.append("秘密功能模块")
    state.human_confirmations[-1].metadata[DECISION_METADATA_KEY][
        "selected_top_level_chapters"
    ] = ["引言", "秘密功能模块"]
    store.save_state(state)

    with pytest.raises(ValueError, match="一级目录不得包含"):
        FrozenDocPlanService(store).freeze_confirmed_plan(run_id)


def test_freeze_rejects_normalized_forbidden_feature_title_variant(
    tmp_path: Path,
) -> None:
    store, run_id = _confirmed_state(tmp_path)
    state = store.load_state(run_id)
    assert state.template_strategy is not None
    state.template_strategy.recommended_chapters.append("模型 训练（功能）")
    state.human_confirmations[-1].metadata[DECISION_METADATA_KEY][
        "selected_top_level_chapters"
    ] = ["引言", "模型 训练（功能）"]
    store.save_state(state)

    with pytest.raises(ValueError, match="一级目录不得包含"):
        FrozenDocPlanService(store).freeze_confirmed_plan(run_id)


def test_freeze_rejects_feature_allowed_and_forbidden_at_the_same_time(
    tmp_path: Path,
) -> None:
    store, run_id = _confirmed_state(tmp_path)
    state = store.load_state(run_id)
    state.product_profile.uncertain_features.append("数据集管理")
    store.save_state(state)

    with pytest.raises(ValueError, match="allowed_current_feature_names"):
        FrozenDocPlanService(store).freeze_confirmed_plan(run_id)


def test_freeze_records_missing_product_name_without_inventing_it(tmp_path: Path) -> None:
    store, run_id = _confirmed_state(tmp_path)
    result = FrozenDocPlanService(store).freeze_confirmed_plan(run_id)
    plan = result.frozen_doc_plan
    assert plan is not None
    assert plan.software_identity["target_product_name"] == ""
    assert plan.missing_information
    assert "软件名称待补充" in plan.risk_notes
