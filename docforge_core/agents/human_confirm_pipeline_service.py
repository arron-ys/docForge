"""MVP pipeline for accepting a recommendation and freezing its plan."""

from docforge_core.domain.schemas import DocForgeState

from .frozen_doc_plan_service import FrozenDocPlanService
from .human_confirm_gate import HumanConfirmGate


class HumanConfirmPipelineService:
    """Run prepare, accept-recommendation confirmation, and plan freezing."""

    def __init__(
        self,
        human_confirm_gate: HumanConfirmGate | None = None,
        frozen_doc_plan_service: FrozenDocPlanService | None = None,
    ) -> None:
        self.human_confirm_gate = human_confirm_gate or HumanConfirmGate()
        self.frozen_doc_plan_service = frozen_doc_plan_service or FrozenDocPlanService()

    def accept_recommendation_and_freeze(
        self,
        run_id: str,
        user_notes: str | None = None,
        risk_acknowledged: bool = False,
    ) -> DocForgeState:
        state = self.human_confirm_gate.prepare_confirmation(run_id)
        decision = self.human_confirm_gate.build_default_decision(state)
        decision.user_notes = user_notes
        decision.risk_acknowledged = risk_acknowledged
        if risk_acknowledged and state.template_strategy is not None:
            decision.acknowledged_risk_chapters = list(
                state.template_strategy.risk_chapters
            )
        self.human_confirm_gate.confirm_template_strategy(run_id, decision)
        return self.frozen_doc_plan_service.freeze_confirmed_plan(run_id)
