from pathlib import Path

import pytest

from docforge_core.agents.human_confirm_gate import (
    DECISION_METADATA_KEY,
    HumanConfirmGate,
)
from docforge_core.domain.enums import (
    ConfirmationStatus,
    ConfirmationType,
    NextAction,
    WorkflowStatus,
)
from docforge_core.domain.schemas import DiagnosisResult, TemplateStrategy

from .agent_helpers import save_state


def _ready_state(tmp_path: Path, risk_chapters: list[str] | None = None):
    store, state = save_state(tmp_path, WorkflowStatus.TEMPLATE_RECOMMENDED)
    state.diagnosis_result = DiagnosisResult(primary_type="Web/SaaS 平台")
    state.template_strategy = TemplateStrategy(
        base_template_id="TEMPLATE_WEB",
        base_template_name="Web 模板",
        enhancement_pack_ids=["PACK_DATA_PLATFORM"],
        recommended_chapters=["引言", "核心功能说明"],
        optional_chapters=["附录"],
        risk_chapters=risk_chapters or [],
    )
    store.save_state(state)
    return store, state


def test_prepare_confirmation_requires_template_recommended(tmp_path: Path) -> None:
    store, state = save_state(tmp_path, WorkflowStatus.DIAGNOSED)
    with pytest.raises(ValueError, match="TEMPLATE_RECOMMENDED"):
        HumanConfirmGate(store).prepare_confirmation(state.run_id)


def test_prepare_confirmation_requires_template_strategy(tmp_path: Path) -> None:
    store, state = save_state(tmp_path, WorkflowStatus.TEMPLATE_RECOMMENDED)
    state.diagnosis_result = DiagnosisResult(primary_type="Web/SaaS 平台")
    store.save_state(state)
    with pytest.raises(ValueError, match="template_strategy"):
        HumanConfirmGate(store).prepare_confirmation(state.run_id)


def test_prepare_confirmation_creates_one_pending_confirmation(tmp_path: Path) -> None:
    store, state = _ready_state(tmp_path)
    gate = HumanConfirmGate(store)

    first = gate.prepare_confirmation(state.run_id)
    second = gate.prepare_confirmation(state.run_id)

    pending = [
        item
        for item in second.human_confirmations
        if item.confirmation_type == ConfirmationType.TEMPLATE_STRATEGY
        and item.status == ConfirmationStatus.PENDING
    ]
    assert len(pending) == 1
    assert first.workflow_status == WorkflowStatus.USER_CONFIRM_REQUIRED
    assert second.next_action == NextAction.ASK_HUMAN_CONFIRMATION
    assert second.frozen_doc_plan is None


def test_build_default_decision_uses_template_strategy(tmp_path: Path) -> None:
    store, state = _ready_state(tmp_path)
    decision = HumanConfirmGate(store).build_default_decision(state)

    assert decision.accepted_recommendation is True
    assert decision.selected_base_template_id == "TEMPLATE_WEB"
    assert decision.selected_enhancement_pack_ids == ["PACK_DATA_PLATFORM"]
    assert decision.selected_top_level_chapters == ["引言", "核心功能说明"]
    assert decision.selected_optional_chapters == []
    assert decision.risk_acknowledged is False


def test_confirm_template_strategy_requires_user_confirm_required(tmp_path: Path) -> None:
    store, state = _ready_state(tmp_path)
    gate = HumanConfirmGate(store)
    decision = gate.build_default_decision(state)
    with pytest.raises(ValueError, match="USER_CONFIRM_REQUIRED"):
        gate.confirm_template_strategy(state.run_id, decision)


def test_confirm_template_strategy_requires_pending_confirmation(tmp_path: Path) -> None:
    store, state = _ready_state(tmp_path)
    state.workflow_status = WorkflowStatus.USER_CONFIRM_REQUIRED
    store.save_state(state)
    gate = HumanConfirmGate(store)
    decision = gate.build_default_decision(state)
    with pytest.raises(ValueError, match="待确认"):
        gate.confirm_template_strategy(state.run_id, decision)


def test_confirm_template_strategy_records_decision_and_state(tmp_path: Path) -> None:
    store, state = _ready_state(tmp_path)
    gate = HumanConfirmGate(store)
    prepared = gate.prepare_confirmation(state.run_id)
    decision = gate.build_default_decision(prepared)
    decision.user_notes = "接受推荐"

    result = gate.confirm_template_strategy(state.run_id, decision)

    confirmation = result.human_confirmations[0]
    assert confirmation.status == ConfirmationStatus.CONFIRMED
    assert confirmation.user_choice == "accept_recommendation"
    assert confirmation.metadata[DECISION_METADATA_KEY]["user_notes"] == "接受推荐"
    assert result.workflow_status == WorkflowStatus.USER_CONFIRMED
    assert result.next_action == NextAction.FREEZE_DOC_PLAN
    assert result.frozen_doc_plan is None


def test_confirm_template_strategy_requires_risk_acknowledgement(tmp_path: Path) -> None:
    store, state = _ready_state(tmp_path, ["AI 能力当前版本状态待确认"])
    gate = HumanConfirmGate(store)
    prepared = gate.prepare_confirmation(state.run_id)
    decision = gate.build_default_decision(prepared)

    with pytest.raises(ValueError, match="风险"):
        gate.confirm_template_strategy(state.run_id, decision)


def test_confirm_template_strategy_rejects_tampered_base_template_id(
    tmp_path: Path,
) -> None:
    store, state = _ready_state(tmp_path)
    gate = HumanConfirmGate(store)
    prepared = gate.prepare_confirmation(state.run_id)
    decision = gate.build_default_decision(prepared)
    decision.selected_base_template_id = "EVIL_TEMPLATE"

    with pytest.raises(ValueError, match="selected_base_template_id"):
        gate.confirm_template_strategy(state.run_id, decision)


def test_confirm_template_strategy_rejects_unknown_top_level_chapter(
    tmp_path: Path,
) -> None:
    store, state = _ready_state(tmp_path)
    gate = HumanConfirmGate(store)
    prepared = gate.prepare_confirmation(state.run_id)
    decision = gate.build_default_decision(prepared)
    decision.selected_top_level_chapters.append("未知章节")

    with pytest.raises(ValueError, match="未知章节"):
        gate.confirm_template_strategy(state.run_id, decision)


def test_confirm_template_strategy_rejects_unknown_acknowledged_risk_chapter(
    tmp_path: Path,
) -> None:
    store, state = _ready_state(tmp_path)
    gate = HumanConfirmGate(store)
    prepared = gate.prepare_confirmation(state.run_id)
    decision = gate.build_default_decision(prepared)
    decision.acknowledged_risk_chapters = ["未知风险章节"]
    decision.risk_acknowledged = True

    with pytest.raises(ValueError, match="未知风险章节"):
        gate.confirm_template_strategy(state.run_id, decision)


def test_confirm_rejects_selected_risk_missing_from_acknowledged_list(
    tmp_path: Path,
) -> None:
    risk_chapter = "AI 能力当前版本状态待确认"
    store, state = _ready_state(tmp_path, [risk_chapter])
    gate = HumanConfirmGate(store)
    prepared = gate.prepare_confirmation(state.run_id)
    decision = gate.build_default_decision(prepared)
    decision.selected_top_level_chapters.append(risk_chapter)
    decision.risk_acknowledged = True

    with pytest.raises(ValueError, match="acknowledged_risk_chapters"):
        gate.confirm_template_strategy(state.run_id, decision)
