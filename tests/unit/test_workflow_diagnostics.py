import hashlib
import json
from pathlib import Path

from docforge_core.domain.enums import NextAction, WorkflowStatus
from docforge_core.domain.schemas import DraftVersion
from docforge_core.exporters.docx_exporter import DocxExportService
from docforge_core.io.run_paths import get_run_dir, get_state_file
from docforge_core.io.state_store import StateStore
from docforge_core.workflow.diagnostics import WorkflowDiagnosticsService

from .test_docx_exporter import _normal_docx_path, _prepare_v1_passed


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_diagnostics_reports_healthy_terminal_docx_run(tmp_path: Path) -> None:
    store, state = _prepare_v1_passed(tmp_path)
    DocxExportService(store).export_current_docx(state.run_id)

    report = WorkflowDiagnosticsService(store).inspect(state.run_id)

    assert report.is_healthy is True
    assert report.is_terminal is True
    assert report.can_download_docx is True
    assert report.exported_docx_path == str(_normal_docx_path(store, state.run_id))


def test_diagnostics_reports_waiting_for_human_confirmation(tmp_path: Path) -> None:
    store = StateStore(data_dir=tmp_path)
    state = store.create_initial_state()
    state.workflow_status = WorkflowStatus.USER_CONFIRM_REQUIRED
    state.next_action = NextAction.ASK_HUMAN_CONFIRMATION
    store.save_state(state)

    report = WorkflowDiagnosticsService(store).inspect(state.run_id)

    assert report.is_healthy is True
    assert report.needs_human_confirmation is True
    assert report.can_continue is False
    assert "确认" in report.suggested_user_action


def test_diagnostics_reports_missing_state_artifact_ref(tmp_path: Path) -> None:
    store, state = _prepare_v1_passed(tmp_path)
    state = store.load_state(state.run_id)
    state.draft_versions[0].content_ref = "drafts/missing.json"
    store.save_state(state)

    report = WorkflowDiagnosticsService(store).inspect(state.run_id)

    assert report.is_healthy is False
    assert any(issue.code == "artifact_ref_missing" for issue in report.issues)
    assert "文件不完整" in report.user_message


def test_diagnostics_reports_hash_mismatch(tmp_path: Path) -> None:
    store, state = _prepare_v1_passed(tmp_path)
    DocxExportService(store).export_current_docx(state.run_id)
    draft_path = get_run_dir(state.run_id, store.data_dir) / "drafts" / "draft_v1.json"
    draft = json.loads(draft_path.read_text(encoding="utf-8"))
    draft["chapters"][0]["sections"][0]["content"] += " tampered"
    draft_path.write_text(json.dumps(draft, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    report = WorkflowDiagnosticsService(store).inspect(state.run_id)

    assert report.is_healthy is False
    assert any(issue.code == "artifact_hash_mismatch" for issue in report.issues)
    assert "可信度" in report.user_message


def test_diagnostics_does_not_modify_state_or_artifacts(tmp_path: Path) -> None:
    store, state = _prepare_v1_passed(tmp_path)
    DocxExportService(store).export_current_docx(state.run_id)
    state_path = get_state_file(state.run_id, store.data_dir)
    docx_path = _normal_docx_path(store, state.run_id)
    before_state_hash = _sha256(state_path)
    before_docx_hash = _sha256(docx_path)

    WorkflowDiagnosticsService(store).inspect(state.run_id)

    assert _sha256(state_path) == before_state_hash
    assert _sha256(docx_path) == before_docx_hash


def test_diagnostics_hides_internal_ids_from_user_message(tmp_path: Path) -> None:
    store = StateStore(data_dir=tmp_path)
    state = store.create_initial_state()
    state.workflow_status = WorkflowStatus.DRAFT_V1_CREATED
    state.next_action = NextAction.PLAN_FIGURE_SLOTS
    state.current_draft_version = "v1"
    state.draft_versions.append(
        DraftVersion(
            draft_id="draft_ev_secret",
            version_label="v1",
            based_on_plan_id="plan",
            based_on_outline_id="outline",
            content_ref="drafts/missing_ev_secret.json",
        )
    )
    store.save_state(state)

    report = WorkflowDiagnosticsService(store).inspect(state.run_id)

    assert report.is_healthy is False
    assert "ev_secret" not in report.user_message
    assert "source_id" not in report.user_message
