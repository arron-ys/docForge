from pathlib import Path

from docforge_core.domain.enums import DraftVersionLabel, ExportType, NextAction, WorkflowStatus
from docforge_core.domain.schemas import DraftVersion, ExportResult
from docforge_core.io.run_paths import get_run_dir
from docforge_core.io.state_store import StateStore
from docforge_core.workflow import WorkflowOrchestratorService, WorkflowServiceRegistry


class FakeWriter:
    def __init__(self, store: StateStore) -> None:
        self.store = store

    def write_v1_draft(self, run_id: str):
        state = self.store.load_state(run_id)
        run_dir = get_run_dir(run_id, self.store.data_dir)
        draft_path = run_dir / "drafts" / "draft_v1.json"
        draft_path.parent.mkdir(parents=True, exist_ok=True)
        draft_path.write_text('{"draft_id":"draft_v1","chapters":[]}\n', encoding="utf-8")
        state.draft_versions.append(
            DraftVersion(
                draft_id="draft_v1",
                version_label=DraftVersionLabel.V1,
                based_on_plan_id="plan",
                based_on_outline_id="outline",
                content_ref="drafts/draft_v1.json",
            )
        )
        state.current_draft_id = "draft_v1"
        state.current_draft_version = "v1"
        state.workflow_status = WorkflowStatus.DRAFT_V1_CREATED
        state.next_action = NextAction.PLAN_FIGURE_SLOTS
        self.store.save_state(state)
        return state


class FakeFigureSlotPlanner:
    def __init__(self, store: StateStore) -> None:
        self.store = store

    def plan_figure_slots(self, run_id: str):
        state = self.store.load_state(run_id)
        run_dir = get_run_dir(run_id, self.store.data_dir)
        target = run_dir / "drafts" / "figure_slots_v1.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text('{"result_id":"figures_v1","figure_slots":[]}\n', encoding="utf-8")
        state.figure_slots_ref = "drafts/figure_slots_v1.json"
        state.figure_slots_result_id = "figures_v1"
        state.workflow_status = WorkflowStatus.FIGURE_SLOTS_PLANNED
        state.next_action = NextAction.AUDIT_DRAFT
        self.store.save_state(state)
        return state


class FakeAuditor:
    def __init__(self, store: StateStore) -> None:
        self.store = store

    def audit_draft(self, run_id: str):
        return self._write_audit(run_id, 1, WorkflowStatus.DRAFT_AUDITED)

    def _write_audit(
        self,
        run_id: str,
        version: int,
        status: WorkflowStatus,
    ):
        state = self.store.load_state(run_id)
        run_dir = get_run_dir(run_id, self.store.data_dir)
        target = run_dir / "drafts" / f"audit_report_v{version}.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f'{{"report_id":"audit_v{version}"}}\n', encoding="utf-8")
        state.audit_report_ref = f"drafts/audit_report_v{version}.json"
        state.audit_report_result_id = f"audit_v{version}"
        state.workflow_status = status
        state.next_action = NextAction.RUN_DRAFT_QUALITY_GATE
        self.store.save_state(state)
        return state


class FakeRevisionLoop:
    def __init__(self, store: StateStore, *, risk_path: bool = False) -> None:
        self.store = store
        self.risk_path = risk_path

    def run_quality_gate_for_current_draft(self, run_id: str):
        state = self.store.load_state(run_id)
        version = int((state.current_draft_version or "v1")[1])
        run_dir = get_run_dir(run_id, self.store.data_dir)
        target = run_dir / "drafts" / f"quality_gate_report_v{version}.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f'{{"draft_version":"v{version}"}}\n', encoding="utf-8")
        state.draft_quality_gate_report_ref = f"drafts/quality_gate_report_v{version}.json"
        if not self.risk_path:
            state.workflow_status = WorkflowStatus.DRAFT_QUALITY_GATE_PASSED
            state.next_action = NextAction.EXPORT_DOCX
        elif version < 3:
            state.workflow_status = WorkflowStatus.DRAFT_REVISION_REQUIRED
            state.next_action = NextAction.REVISE_DRAFT
        else:
            state.workflow_status = WorkflowStatus.RISK_VERSION_READY
            state.next_action = NextAction.EXPORT_RISK_DOCX
        self.store.save_state(state)
        return state

    def revise_current_draft(self, run_id: str):
        state = self.store.load_state(run_id)
        next_version = 2 if state.current_draft_version == "v1" else 3
        run_dir = get_run_dir(run_id, self.store.data_dir)
        target = run_dir / "drafts" / f"draft_v{next_version}.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            f'{{"draft_id":"draft_v{next_version}","chapters":[]}}\n',
            encoding="utf-8",
        )
        state.draft_versions.append(
            DraftVersion(
                draft_id=f"draft_v{next_version}",
                version_label=DraftVersionLabel(f"v{next_version}"),
                based_on_plan_id="plan",
                based_on_outline_id="outline",
                content_ref=f"drafts/draft_v{next_version}.json",
            )
        )
        state.current_draft_id = f"draft_v{next_version}"
        state.current_draft_version = f"v{next_version}"
        state.workflow_status = (
            WorkflowStatus.DRAFT_V2_CREATED
            if next_version == 2
            else WorkflowStatus.DRAFT_V3_CREATED
        )
        state.next_action = NextAction.AUDIT_REVISED_DRAFT
        self.store.save_state(state)
        return state

    def audit_revised_draft(self, run_id: str):
        state = self.store.load_state(run_id)
        version = int((state.current_draft_version or "v2")[1])
        return FakeAuditor(self.store)._write_audit(
            run_id,
            version,
            WorkflowStatus.DRAFT_V2_AUDITED
            if version == 2
            else WorkflowStatus.DRAFT_V3_AUDITED,
        )


class FakeDocxExporter:
    def __init__(self, store: StateStore) -> None:
        self.store = store

    def export_current_docx(self, run_id: str):
        state = self.store.load_state(run_id)
        run_dir = get_run_dir(run_id, self.store.data_dir)
        is_risk = state.workflow_status == WorkflowStatus.RISK_VERSION_READY
        docx_name = "risk.docx" if is_risk else "final.docx"
        target = run_dir / "exports" / docx_name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"docx")
        state.export_result = ExportResult(
            export_type=ExportType.RISK if is_risk else ExportType.FINAL,
            docx_path=f"exports/{docx_name}",
        )
        state.final_doc_path = f"exports/{docx_name}"
        state.workflow_status = (
            WorkflowStatus.RISK_EXPORTED if is_risk else WorkflowStatus.FINAL_EXPORTED
        )
        state.next_action = NextAction.STOP
        self.store.save_state(state)
        return state.export_result


def _orchestrator(store: StateStore, *, risk_path: bool) -> WorkflowOrchestratorService:
    return WorkflowOrchestratorService(
        store,
        WorkflowServiceRegistry(
            writer_agent=FakeWriter(store),
            figure_slot_planner=FakeFigureSlotPlanner(store),
            audit_agent=FakeAuditor(store),
            revision_loop_service=FakeRevisionLoop(store, risk_path=risk_path),
            docx_export_service=FakeDocxExporter(store),
        ),
    )


def _ready_run(tmp_path: Path) -> tuple[StateStore, str]:
    store = StateStore(data_dir=tmp_path)
    state = store.create_initial_state()
    state.workflow_status = WorkflowStatus.PLAN_GATE_PASSED
    state.next_action = NextAction.WRITE_DRAFT
    store.save_state(state)
    return store, state.run_id


def _assert_only_allowed_user_export(run_dir: Path, expected_name: str) -> None:
    assert (run_dir / "exports" / expected_name).exists()
    forbidden_suffixes = {".pdf", ".md", ".markdown", ".png", ".jpg", ".jpeg", ".webp"}
    for path in run_dir.rglob("*"):
        if path.is_file():
            assert path.suffix.lower() not in forbidden_suffixes
    assert not (run_dir / "exports" / "manifest.json").exists()
    assert not (run_dir / "exports" / "export_manifest.json").exists()


def test_artifact_level_e2e_passed_v1_exports_normal_docx(tmp_path: Path) -> None:
    store, run_id = _ready_run(tmp_path)

    summary = _orchestrator(store, risk_path=False).run_until_terminal(run_id)

    assert summary.success is True
    assert summary.terminal is True
    assert summary.workflow_status == WorkflowStatus.FINAL_EXPORTED.value
    assert summary.docx_path == "exports/final.docx"
    state = store.load_state(run_id)
    assert state.export_result is not None
    assert state.export_result.pdf_path is None
    assert state.final_pdf_path is None
    _assert_only_allowed_user_export(get_run_dir(run_id, store.data_dir), "final.docx")


def test_artifact_level_e2e_failed_v3_exports_risk_docx(tmp_path: Path) -> None:
    store, run_id = _ready_run(tmp_path)

    summary = _orchestrator(store, risk_path=True).run_until_terminal(run_id)

    assert summary.success is True
    assert summary.terminal is True
    assert summary.workflow_status == WorkflowStatus.RISK_EXPORTED.value
    assert summary.docx_path == "exports/risk.docx"
    state = store.load_state(run_id)
    assert state.current_draft_version == "v3"
    assert state.export_result is not None
    assert state.export_result.export_type == ExportType.RISK
    assert state.export_result.pdf_path is None
    assert state.final_pdf_path is None
    _assert_only_allowed_user_export(get_run_dir(run_id, store.data_dir), "risk.docx")
