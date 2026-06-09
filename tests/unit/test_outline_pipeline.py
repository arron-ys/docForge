from pathlib import Path

from docforge_core.agents.outline_agent import OutlineAgent
from docforge_core.domain.enums import NextAction, WorkflowStatus
from docforge_core.gates.plan_quality_gate import PlanQualityGate

from .outline_helpers import SafeWritingPlanSafetyVerifier, frozen_plan_state


def test_outline_pipeline_reaches_plan_gate_passed_without_draft_or_export(
    tmp_path: Path,
) -> None:
    store, state = frozen_plan_state(tmp_path)

    verifier = SafeWritingPlanSafetyVerifier()
    outlined = OutlineAgent(
        store,
        writing_plan_safety_verifier=verifier,
    ).create_outline(state.run_id)
    assert outlined.workflow_status == WorkflowStatus.OUTLINE_CREATED
    assert outlined.next_action == NextAction.RUN_PLAN_QUALITY_GATE

    result = PlanQualityGate(
        store,
        writing_plan_safety_verifier=verifier,
    ).run(state.run_id)

    assert result.workflow_status == WorkflowStatus.PLAN_GATE_PASSED
    assert result.next_action == NextAction.WRITE_DRAFT
    assert result.draft_versions == []
    assert result.current_draft_id is None
    assert result.export_result is None
    assert result.final_doc_path is None
