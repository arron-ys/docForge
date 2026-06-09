"""Human confirmation gate for template strategy decisions."""

from __future__ import annotations

from datetime import UTC, datetime

from docforge_core.domain.enums import (
    ConfirmationStatus,
    ConfirmationType,
    NextAction,
    WorkflowStatus,
)
from docforge_core.domain.schemas import (
    DocForgeState,
    HumanConfirmation,
    TemplateConfirmationDecision,
)
from docforge_core.io.state_store import StateStore

from ._shared import transition
from .confirmation_decision_validator import validate_template_confirmation_decision

DECISION_METADATA_KEY = "template_confirmation_decision"


class HumanConfirmGate:
    """Prepare and record a human decision without freezing the plan."""

    def __init__(self, state_store: StateStore | None = None) -> None:
        self.state_store = state_store or StateStore()

    def prepare_confirmation(self, run_id: str) -> DocForgeState:
        state = self.state_store.load_state(run_id)
        pending = self._pending_template_confirmation(state)
        if state.workflow_status == WorkflowStatus.USER_CONFIRM_REQUIRED and pending is not None:
            return state
        if state.workflow_status != WorkflowStatus.TEMPLATE_RECOMMENDED:
            raise ValueError("准备用户确认要求 workflow_status 为 TEMPLATE_RECOMMENDED")
        if state.template_strategy is None:
            raise ValueError("准备用户确认要求存在 template_strategy")
        if state.diagnosis_result is None:
            raise ValueError("准备用户确认要求存在 diagnosis_result")

        state.human_confirmations.append(
            HumanConfirmation(
                confirmation_type=ConfirmationType.TEMPLATE_STRATEGY,
                prompt=(
                    "请确认推荐模板、增强包和一级章节。风险章节不会自动进入当前功能范围，"
                    "如需继续冻结必须明确知晓风险。"
                ),
                options=["accept_recommendation", "reject_or_modify"],
            )
        )
        transition(
            state,
            WorkflowStatus.TEMPLATE_RECOMMENDED,
            WorkflowStatus.USER_CONFIRM_REQUIRED,
            NextAction.ASK_HUMAN_CONFIRMATION,
            "HumanConfirmGate.prepare_confirmation",
            "template strategy confirmation required",
        )
        self.state_store.save_state(state)
        return state

    def build_default_decision(self, state: DocForgeState) -> TemplateConfirmationDecision:
        strategy = state.template_strategy
        if strategy is None:
            raise ValueError("构造默认确认决策要求存在 template_strategy")
        return TemplateConfirmationDecision(
            accepted_recommendation=True,
            selected_base_template_id=strategy.base_template_id,
            selected_base_template_name=strategy.base_template_name,
            selected_enhancement_pack_ids=list(strategy.enhancement_pack_ids),
            selected_top_level_chapters=list(strategy.recommended_chapters),
            selected_optional_chapters=[],
            acknowledged_risk_chapters=[],
            excluded_chapters=[],
            risk_acknowledged=False,
        )

    def confirm_template_strategy(
        self,
        run_id: str,
        decision: TemplateConfirmationDecision,
    ) -> DocForgeState:
        state = self.state_store.load_state(run_id)
        if state.workflow_status != WorkflowStatus.USER_CONFIRM_REQUIRED:
            raise ValueError("确认模板策略要求 workflow_status 为 USER_CONFIRM_REQUIRED")
        confirmation = self._pending_template_confirmation(state)
        if confirmation is None:
            raise ValueError("不存在待确认的 template_strategy HumanConfirmation")
        strategy = state.template_strategy
        if strategy is None:
            raise ValueError("确认模板策略要求存在 template_strategy")

        validate_template_confirmation_decision(decision, strategy)
        confirmed_at = datetime.now(UTC).isoformat()
        decision.confirmed_at = confirmed_at
        confirmation.status = ConfirmationStatus.CONFIRMED
        confirmation.user_choice = (
            "accept_recommendation"
            if decision.accepted_recommendation
            else "manual_override"
        )
        confirmation.user_notes = decision.user_notes
        confirmation.confirmed_at = confirmed_at
        confirmation.metadata[DECISION_METADATA_KEY] = decision.model_dump(mode="json")
        transition(
            state,
            WorkflowStatus.USER_CONFIRM_REQUIRED,
            WorkflowStatus.USER_CONFIRMED,
            NextAction.FREEZE_DOC_PLAN,
            "HumanConfirmGate.confirm_template_strategy",
            "template strategy confirmed by human",
        )
        self.state_store.save_state(state)
        return state

    @staticmethod
    def _pending_template_confirmation(state: DocForgeState) -> HumanConfirmation | None:
        return next(
            (
                item
                for item in state.human_confirmations
                if item.confirmation_type == ConfirmationType.TEMPLATE_STRATEGY
                and item.status == ConfirmationStatus.PENDING
            ),
            None,
        )
