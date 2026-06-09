from pathlib import Path

import pytest

from docforge_core.domain.enums import NextAction, WorkflowStatus
from docforge_core.exporters.docx_acceptance import DocxAcceptanceChecker
from docforge_core.exporters.docx_exporter import DocxExportService
from docforge_core.io.run_paths import get_run_dir
from docforge_core.workflow.diagnostics import WorkflowDiagnosticsService
from docforge_core.workflow.e2e_sample_runner import load_e2e_sample_project

from .test_upload_level_e2e import (
    _confirm_minimal_chapters,
    _new_sample_run,
    _orchestrator,
    _run_sample_to_terminal,
    _sha256,
)


def test_product_acceptance_sample_project_normal_docx(tmp_path: Path) -> None:
    store, run_id, docx_path = _run_sample_to_terminal(tmp_path)

    health = WorkflowDiagnosticsService(store).inspect(run_id)
    acceptance = DocxAcceptanceChecker().check_normal_docx(
        docx_path,
        store.load_state(run_id),
    )

    assert health.is_healthy is True
    assert health.can_download_docx is True
    assert acceptance.passed is True


def test_product_acceptance_resume_after_confirmation(tmp_path: Path) -> None:
    store, run_id = _new_sample_run(tmp_path)
    orchestrator = _orchestrator(store)
    assert orchestrator.run_until_human_confirmation_required(run_id).waiting_for_human_confirmation

    _confirm_minimal_chapters(store, orchestrator, run_id)
    summary = _orchestrator(store).resume(run_id)

    assert summary.terminal is True
    assert WorkflowDiagnosticsService(store).inspect(run_id).can_download_docx is True


def test_product_acceptance_resume_after_audit(tmp_path: Path) -> None:
    store, run_id = _new_sample_run(tmp_path)
    orchestrator = _orchestrator(store)
    assert orchestrator.run_until_human_confirmation_required(run_id).waiting_for_human_confirmation
    _confirm_minimal_chapters(store, orchestrator, run_id)
    while store.load_state(run_id).audit_report_ref is None:
        summary = orchestrator.run_next_step(run_id)
        assert summary.success is True

    audit_hash = _sha256(get_run_dir(run_id, store.data_dir) / "drafts" / "audit_report_v1.json")
    summary = _orchestrator(store).resume(run_id)

    assert summary.terminal is True
    assert _sha256(get_run_dir(run_id, store.data_dir) / "drafts" / "audit_report_v1.json") == audit_hash


def test_product_acceptance_repeated_continue_does_not_duplicate_artifacts(
    tmp_path: Path,
) -> None:
    store, run_id, _docx_path = _run_sample_to_terminal(tmp_path)
    before = store.load_state(run_id)
    run_dir = get_run_dir(run_id, store.data_dir)
    files_before = sorted(str(path.relative_to(run_dir)) for path in run_dir.rglob("*") if path.is_file())

    summary = _orchestrator(store).run_until_terminal(run_id)

    after = store.load_state(run_id)
    files_after = sorted(str(path.relative_to(run_dir)) for path in run_dir.rglob("*") if path.is_file())
    assert summary.terminal is True
    assert len(after.draft_versions) == len(before.draft_versions)
    assert files_after == files_before


def test_product_acceptance_existing_docx_does_not_overwrite_without_force(
    tmp_path: Path,
) -> None:
    store, run_id, docx_path = _run_sample_to_terminal(tmp_path)
    before_hash = _sha256(docx_path)
    state = store.load_state(run_id)
    state.workflow_status = WorkflowStatus.DRAFT_QUALITY_GATE_PASSED
    state.next_action = NextAction.EXPORT_DOCX
    state.export_result = None
    state.final_doc_path = None
    store.save_state(state)

    with pytest.raises(ValueError, match="force=False|目标 DOCX 已存在"):
        DocxExportService(store).export_current_docx(run_id)

    assert _sha256(docx_path) == before_hash


def test_product_acceptance_docx_acceptance_checker_passes(tmp_path: Path) -> None:
    store, run_id, docx_path = _run_sample_to_terminal(tmp_path)

    report = DocxAcceptanceChecker().check_normal_docx(docx_path, store.load_state(run_id))

    assert report.passed is True


def test_product_acceptance_internal_artifacts_not_user_downloadable() -> None:
    source = Path("app/main.py").read_text(encoding="utf-8")
    panel = source.split("def _render_workflow_panel", 1)[1].split(
        "def _run_workflow_action",
        1,
    )[0]

    assert "_render_docx_download" in panel
    assert "manifest" not in panel.lower()
    assert "audit" not in panel.lower()
    assert "evidence" not in panel.lower()
    assert "state.json" not in panel


def test_product_acceptance_sample_loader_repeated_click_is_idempotent(
    tmp_path: Path,
) -> None:
    store, run_id = _new_sample_run(tmp_path)

    second = load_e2e_sample_project(store, run_id)

    assert second.skipped_existing is True
    assert second.imported_count == 0
    assert len(store.load_state(run_id).source_registry) == 6
