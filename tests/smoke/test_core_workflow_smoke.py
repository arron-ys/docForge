from pathlib import Path

from docforge_core.domain.enums import NextAction, WorkflowStatus
from docforge_core.io.run_paths import get_run_dir
from docforge_core.workflow.diagnostics import WorkflowDiagnosticsService

from tests.helpers.e2e_workflow_helpers import (
    _confirm_minimal_chapters,
    _new_sample_run,
    _orchestrator,
)


def test_core_upload_to_downloadable_docx_smoke(tmp_path: Path) -> None:
    store, run_id = _new_sample_run(tmp_path)
    orchestrator = _orchestrator(store)

    summary = orchestrator.run_until_human_confirmation_required(run_id)

    state = store.load_state(run_id)
    assert summary.success is True
    assert summary.waiting_for_human_confirmation is True
    assert state.workflow_status == WorkflowStatus.USER_CONFIRM_REQUIRED
    assert state.next_action == NextAction.ASK_HUMAN_CONFIRMATION

    _confirm_minimal_chapters(store, orchestrator, run_id)
    summary = orchestrator.run_until_terminal(run_id)

    state = store.load_state(run_id)
    assert summary.success is True
    assert summary.terminal is True
    assert state.workflow_status == WorkflowStatus.FINAL_EXPORTED
    assert state.export_result is not None
    assert state.export_result.docx_path is not None
    assert (get_run_dir(run_id, store.data_dir) / state.export_result.docx_path).exists()
    assert WorkflowDiagnosticsService(store).inspect(run_id).can_download_docx is True
