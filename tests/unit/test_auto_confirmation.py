from pathlib import Path

import pytest

from docforge_core.domain.enums import (
    AllowedUsage,
    CorpusType,
    EvidenceStrength,
    EvidenceType,
    FileType,
    NextAction,
    SourceType,
    WorkflowStatus,
)
from docforge_core.domain.schemas import (
    DiagnosisResult,
    DocForgeState,
    EvidenceItem,
    FrozenDocPlan,
    SourceItem,
    TemplateStrategy,
)
from docforge_core.io.run_paths import get_run_dir
from docforge_core.io.state_store import StateStore
from docforge_core.workflow.auto_confirmation import AutoConfirmationPolicy
from docforge_core.workflow.run_settings import get_run_settings, set_run_settings
from docforge_core.workflow.strategy_reset import (
    StrategyResetService,
    StrategyRestartRequiredError,
)


def _product_document() -> SourceItem:
    return SourceItem(
        source_type=SourceType.PRD,
        file_type=FileType.MD,
        corpus_type=CorpusType.PRODUCT_EVIDENCE,
        allowed_usage=AllowedUsage.FACTUAL_EVIDENCE,
        is_product_source=True,
    )


def _confirmation_state(*sources: SourceItem) -> DocForgeState:
    return DocForgeState(
        workflow_status=WorkflowStatus.USER_CONFIRM_REQUIRED,
        next_action=NextAction.ASK_HUMAN_CONFIRMATION,
        source_registry=list(sources) or [_product_document()],
        diagnosis_result=DiagnosisResult(
            primary_type="Web/SaaS 平台",
            primary_type_confidence=0.85,
        ),
        template_strategy=TemplateStrategy(
            base_template_id="TEMPLATE_WEB",
            base_template_name="Web 模板",
            recommended_chapters=["引言", "核心功能说明"],
        ),
    )


def test_auto_confirm_when_agent_judgement_allowed_and_no_conflict() -> None:
    decision = AutoConfirmationPolicy().evaluate(_confirmation_state())

    assert decision.can_auto_confirm is True
    assert decision.selected_product_type == "Web/SaaS 平台"
    assert decision.confirmation_payload is not None
    assert "系统已" not in decision.message
    assert "已根据当前资料自动确认" in decision.message


def test_auto_confirm_when_user_selection_matches_agent_recommendation() -> None:
    state = _confirmation_state()
    set_run_settings(
        state,
        {
            "product_type_hint": "saas_web_platform",
            "doc_output_type": "user_manual",
            "reference_style_strength": "strong",
        },
    )

    decision = AutoConfirmationPolicy().evaluate(state)

    assert decision.can_auto_confirm is True
    assert decision.selected_product_type == "SaaS / Web 平台"
    assert "与资料判断一致" in decision.message


def test_do_not_auto_confirm_when_user_selection_conflicts_with_agent() -> None:
    state = _confirmation_state()
    set_run_settings(state, {"product_type_hint": "industrial_software"})

    decision = AutoConfirmationPolicy().evaluate(state)

    assert decision.can_auto_confirm is False
    assert decision.product_type_conflict is True
    assert decision.conflicts


def test_do_not_auto_confirm_with_reference_only() -> None:
    reference = SourceItem(
        source_type=SourceType.REFERENCE_SOFT_COPYRIGHT_DOC,
        file_type=FileType.PDF,
        corpus_type=CorpusType.REFERENCE_STYLE,
        allowed_usage=AllowedUsage.STYLE_ONLY,
        is_reference_source=True,
    )

    decision = AutoConfirmationPolicy().evaluate(_confirmation_state(reference))

    assert decision.can_auto_confirm is False
    assert "只有外部参考资料" in decision.reason


def test_do_not_auto_confirm_with_screenshot_only() -> None:
    screenshot = SourceItem(
        source_type=SourceType.SCREENSHOT,
        file_type=FileType.PNG,
        corpus_type=CorpusType.PRODUCT_EVIDENCE,
        allowed_usage=AllowedUsage.DISPLAY_MATERIAL_ONLY,
        is_product_source=True,
    )

    decision = AutoConfirmationPolicy().evaluate(_confirmation_state(screenshot))

    assert decision.can_auto_confirm is False
    assert "只有产品截图" in decision.reason


def test_auto_confirmation_preserves_evidence_boundary() -> None:
    state = _confirmation_state()
    state.evidence_map = [
        EvidenceItem.model_construct(
            source_id="external-reference",
            source_type=SourceType.REFERENCE_SOFT_COPYRIGHT_DOC,
            file_type=FileType.PDF,
            evidence_type=EvidenceType.PRODUCT_DOCUMENT,
            corpus_type=CorpusType.PRODUCT_EVIDENCE,
            allowed_usage=AllowedUsage.FACTUAL_EVIDENCE,
            evidence_strength=EvidenceStrength.MEDIUM,
        )
    ]

    decision = AutoConfirmationPolicy().evaluate(state)

    assert decision.can_auto_confirm is False
    assert "外部参考资料被标记为产品事实证据" in decision.reason


def test_strategy_change_before_freeze_updates_run_settings(tmp_path: Path) -> None:
    store = StateStore(data_dir=tmp_path)
    state = store.create_initial_state()
    state.source_registry = [_product_document()]
    state.workflow_status = WorkflowStatus.USER_CONFIRM_REQUIRED
    state.next_action = NextAction.ASK_HUMAN_CONFIRMATION
    state.diagnosis_result = DiagnosisResult(primary_type="Web/SaaS 平台")
    state.template_strategy = TemplateStrategy(
        base_template_id="TEMPLATE_WEB",
        base_template_name="Web 模板",
        recommended_chapters=["引言"],
    )
    store.save_state(state)

    updated = StrategyResetService(store).update_settings(
        state.run_id,
        {
            "product_type_hint": "industrial_software",
            "doc_output_type": "technical_design",
            "reference_style_strength": "weak",
        },
    )

    assert get_run_settings(updated)["product_type_hint"] == "industrial_software"
    assert updated.template_strategy is None
    assert updated.frozen_doc_plan is None
    assert updated.workflow_status == WorkflowStatus.MATERIAL_UPLOADED


def test_strategy_change_after_freeze_requires_restart(tmp_path: Path) -> None:
    store = StateStore(data_dir=tmp_path)
    state = store.create_initial_state()
    state.source_registry = [_product_document()]
    state.workflow_status = WorkflowStatus.PLAN_FROZEN
    state.next_action = NextAction.CREATE_OUTLINE
    state.frozen_doc_plan = FrozenDocPlan(locked_status="locked")
    store.save_state(state)

    with pytest.raises(StrategyRestartRequiredError):
        StrategyResetService(store).update_settings(state.run_id, get_run_settings(state))

    run_dir = get_run_dir(state.run_id, store.data_dir)
    draft = run_dir / "drafts" / "old.json"
    export = run_dir / "exports" / "old.docx"
    draft.write_text("old", encoding="utf-8")
    export.write_bytes(b"old")

    restarted = StrategyResetService(store).update_settings(
        state.run_id,
        {
            "product_type_hint": "agent_decide",
            "doc_output_type": "user_manual",
            "reference_style_strength": "medium",
        },
        allow_restart=True,
    )

    assert restarted.frozen_doc_plan is None
    assert restarted.source_registry
    assert restarted.workflow_status == WorkflowStatus.MATERIAL_UPLOADED
    assert not draft.exists()
    assert not export.exists()
