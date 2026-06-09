from pathlib import Path

from docforge_core.agents._shared import AI_NON_CURRENT_RISK_PREFIX
from docforge_core.agents.template_strategy_agent import TemplateStrategyAgent
from docforge_core.domain.enums import CapabilityType, WorkflowStatus
from docforge_core.domain.schemas import DiagnosisResult, ProductCapability, ProductProfile

from .agent_helpers import capability, product_evidence, save_state


def _strategy(
    tmp_path: Path,
    enhancement_tags: list[str],
    risk_notes: list[str] | None = None,
    with_evidence: bool = False,
    evidence_summary: str = "raw evidence should not influence template",
    primary_type: str = "通用软件系统",
    product_profile: ProductProfile | None = None,
    product_capabilities: list[ProductCapability] | None = None,
):
    store, state = save_state(
        tmp_path,
        WorkflowStatus.DIAGNOSED,
        [product_evidence(summary=evidence_summary)]
        if with_evidence
        else [],
    )
    state.diagnosis_result = DiagnosisResult(
        primary_type=primary_type,
        enhancement_tags=enhancement_tags,
        risk_notes=risk_notes or [],
    )
    state.product_profile = product_profile or ProductProfile()
    state.product_capabilities = product_capabilities or []
    store.save_state(state)
    return TemplateStrategyAgent(state_store=store).recommend_run(state.run_id).template_strategy


def test_no_ai_tag_means_no_ai_pack(tmp_path: Path) -> None:
    strategy = _strategy(tmp_path, [])
    assert strategy is not None
    assert "PACK_AI_LIGHT" not in strategy.enhancement_pack_ids


def test_no_data_tag_means_no_data_pack(tmp_path: Path) -> None:
    strategy = _strategy(tmp_path, [])
    assert strategy is not None
    assert "PACK_DATA_PLATFORM" not in strategy.enhancement_pack_ids


def test_data_tag_adds_data_pack(tmp_path: Path) -> None:
    strategy = _strategy(tmp_path, ["数据平台"])
    assert strategy is not None
    assert "PACK_DATA_PLATFORM" in strategy.enhancement_pack_ids


def test_ai_tag_adds_ai_pack(tmp_path: Path) -> None:
    strategy = _strategy(tmp_path, ["AI 平台"])
    assert strategy is not None
    assert "PACK_AI_LIGHT" in strategy.enhancement_pack_ids


def test_planned_ai_risk_without_tag_only_adds_risk_chapter(tmp_path: Path) -> None:
    strategy = _strategy(tmp_path, [], [AI_NON_CURRENT_RISK_PREFIX])
    assert strategy is not None
    assert "PACK_AI_LIGHT" not in strategy.enhancement_pack_ids
    assert "模型相关功能" not in strategy.recommended_chapters
    assert "AI 能力当前版本状态待确认" in strategy.risk_chapters


def test_template_strategy_does_not_read_raw_evidence(tmp_path: Path) -> None:
    strategy = _strategy(tmp_path, [], with_evidence=True)
    assert strategy is not None
    assert strategy.enhancement_pack_ids == []


def test_web_saas_without_data_tag_does_not_add_data_chapters(tmp_path: Path) -> None:
    strategy = _strategy(tmp_path, [], primary_type="Web/SaaS 平台")
    assert strategy is not None
    assert "PACK_DATA_PLATFORM" not in strategy.enhancement_pack_ids
    assert not {
        "数据管理功能",
        "数据资产管理",
        "数据集管理",
        "数据导入与处理",
        "质量检查与报告",
    }.intersection(strategy.recommended_chapters)


def test_web_saas_without_permission_tag_does_not_add_system_management_chapters(
    tmp_path: Path,
) -> None:
    strategy = _strategy(tmp_path, [], primary_type="Web/SaaS 平台")
    assert strategy is not None
    assert "PACK_PERMISSION_MANAGEMENT" not in strategy.enhancement_pack_ids
    assert "用户与权限管理" not in strategy.recommended_chapters
    assert "系统管理功能" not in strategy.recommended_chapters


def test_data_tag_adds_only_data_pack_and_data_chapters(tmp_path: Path) -> None:
    strategy = _strategy(tmp_path, ["数据平台"], primary_type="Web/SaaS 平台")
    assert strategy is not None
    assert strategy.enhancement_pack_ids == ["PACK_DATA_PLATFORM"]
    assert {
        "数据资产管理",
        "数据集管理",
        "数据导入与处理",
        "质量检查与报告",
    }.issubset(strategy.recommended_chapters)
    assert "用户与权限管理" not in strategy.recommended_chapters
    assert "模型相关功能" not in strategy.recommended_chapters


def test_permission_tag_adds_permission_pack_and_permission_chapter(
    tmp_path: Path,
) -> None:
    strategy = _strategy(tmp_path, ["权限管理"], primary_type="Web/SaaS 平台")
    assert strategy is not None
    assert strategy.enhancement_pack_ids == ["PACK_PERMISSION_MANAGEMENT"]
    assert "用户与权限管理" in strategy.recommended_chapters


def test_web_base_chapters_are_generic_only(tmp_path: Path) -> None:
    strategy = _strategy(tmp_path, [], primary_type="Web/SaaS 平台")
    assert strategy is not None
    assert {
        "引言",
        "软件概述",
        "运行环境",
        "登录与首页",
        "核心功能说明",
        "用户操作流程",
        "常见问题与附录",
    }.issubset(strategy.recommended_chapters)
    assert not {
        "数据管理功能",
        "系统管理功能",
        "模型相关功能",
        "训练或评测相关功能",
    }.intersection(strategy.recommended_chapters)


def test_template_strategy_does_not_read_product_profile_to_add_chapters(
    tmp_path: Path,
) -> None:
    strategy = _strategy(
        tmp_path,
        [],
        primary_type="Web/SaaS 平台",
        product_profile=ProductProfile(business_objects=["数据集"]),
    )
    assert strategy is not None
    assert "PACK_DATA_PLATFORM" not in strategy.enhancement_pack_ids
    assert "数据集管理" not in strategy.recommended_chapters
    assert "数据资产管理" not in strategy.recommended_chapters


def test_template_strategy_does_not_read_evidence_to_add_chapters(tmp_path: Path) -> None:
    strategy = _strategy(
        tmp_path,
        [],
        with_evidence=True,
        evidence_summary="当前版本支持数据集管理和数据资产管理",
        primary_type="Web/SaaS 平台",
    )
    assert strategy is not None
    assert "PACK_DATA_PLATFORM" not in strategy.enhancement_pack_ids
    assert "数据集管理" not in strategy.recommended_chapters


def test_template_strategy_does_not_read_product_capabilities_to_add_chapters(
    tmp_path: Path,
) -> None:
    strategy = _strategy(
        tmp_path,
        [],
        primary_type="Web/SaaS 平台",
        product_capabilities=[capability("cap_ai", CapabilityType.AI_INFERENCE)],
    )
    assert strategy is not None
    assert "PACK_AI_LIGHT" not in strategy.enhancement_pack_ids
    assert "模型相关功能" not in strategy.recommended_chapters


def test_no_ai_tag_means_no_ai_chapters(tmp_path: Path) -> None:
    strategy = _strategy(tmp_path, [], primary_type="Web/SaaS 平台")
    assert strategy is not None
    assert "PACK_AI_LIGHT" not in strategy.enhancement_pack_ids
    assert "模型相关功能" not in strategy.recommended_chapters
    assert "训练或评测相关功能" not in strategy.recommended_chapters


def test_no_automotive_tag_means_no_automotive_optional_chapter(tmp_path: Path) -> None:
    strategy = _strategy(tmp_path, [], primary_type="Web/SaaS 平台")
    assert strategy is not None
    assert "PACK_AUTO_INDUSTRIAL_SOFTWARE" not in strategy.enhancement_pack_ids
    assert "汽车行业数据对象说明" not in strategy.optional_chapters


def test_ai_tag_without_ai_risk_adds_ai_recommended_chapters(tmp_path: Path) -> None:
    strategy = _strategy(tmp_path, ["AI 平台"], primary_type="Web/SaaS 平台")
    assert strategy is not None
    assert "PACK_AI_LIGHT" in strategy.enhancement_pack_ids
    assert "模型相关功能" in strategy.recommended_chapters
    assert "训练或评测相关功能" in strategy.recommended_chapters
    assert "训练或评测相关功能" not in strategy.risk_chapters


def test_ai_tag_with_ai_risk_moves_training_chapter_to_risks(tmp_path: Path) -> None:
    strategy = _strategy(
        tmp_path,
        ["AI 平台"],
        risk_notes=[AI_NON_CURRENT_RISK_PREFIX],
        primary_type="Web/SaaS 平台",
    )
    assert strategy is not None
    assert "PACK_AI_LIGHT" in strategy.enhancement_pack_ids
    assert "模型相关功能" in strategy.recommended_chapters
    assert "训练或评测相关功能" not in strategy.recommended_chapters
    assert "训练或评测相关功能" in strategy.risk_chapters


def test_unstructured_risk_keywords_do_not_expand_ai_chapters(tmp_path: Path) -> None:
    strategy = _strategy(
        tmp_path,
        [],
        risk_notes=["某个三维模型文件需要人工复核。"],
        primary_type="Web/SaaS 平台",
    )
    assert strategy is not None
    assert "PACK_AI_LIGHT" not in strategy.enhancement_pack_ids
    assert "模型相关功能" not in strategy.recommended_chapters
    assert "AI 能力当前版本状态待确认" not in strategy.risk_chapters


def test_automotive_tag_adds_only_automotive_pack_and_optional_chapter(
    tmp_path: Path,
) -> None:
    strategy = _strategy(tmp_path, ["汽车工业软件"], primary_type="Web/SaaS 平台")
    assert strategy is not None
    assert strategy.enhancement_pack_ids == ["PACK_AUTO_INDUSTRIAL_SOFTWARE"]
    assert strategy.optional_chapters == ["汽车行业数据对象说明"]


def test_unknown_enhancement_tag_does_not_add_pack_or_capability_chapter(
    tmp_path: Path,
) -> None:
    strategy = _strategy(tmp_path, ["未经支持的扩展"], primary_type="Web/SaaS 平台")
    assert strategy is not None
    assert strategy.enhancement_pack_ids == []
    assert strategy.optional_chapters == []
    assert not {
        "数据资产管理",
        "数据集管理",
        "模型相关功能",
        "用户与权限管理",
    }.intersection(strategy.recommended_chapters)
