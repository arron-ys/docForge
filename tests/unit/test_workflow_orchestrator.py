from pathlib import Path

from docforge_core.domain.enums import (
    ConfirmationStatus,
    ConfirmationType,
    DraftVersionLabel,
    ExportType,
    NextAction,
    WorkflowStatus,
)
from docforge_core.domain.schemas import (
    DiagnosisResult,
    DraftVersion,
    EvidenceItem,
    ExportResult,
    FrozenDocPlan,
    HumanConfirmation,
    TemplateConfirmationDecision,
    TemplateStrategy,
)
from docforge_core.io.run_paths import get_run_dir
from docforge_core.io.state_store import StateStore
from docforge_core.workflow import WorkflowOrchestratorService, WorkflowServiceRegistry


class FakeParseService:
    def __init__(self, store: StateStore) -> None:
        self.store = store
        self.calls = 0

    def parse_run(self, run_id: str):
        self.calls += 1
        state = self.store.load_state(run_id)
        state.workflow_status = WorkflowStatus.SOURCE_PARSED
        state.next_action = NextAction.ANALYZE_REFERENCE_STYLE
        self.store.save_state(state)
        return state


class FakeEvidenceService:
    def __init__(self, store: StateStore) -> None:
        self.store = store

    def extract_run(self, run_id: str):
        state = self.store.load_state(run_id)
        state.evidence_map = [
            EvidenceItem(
                evidence_id="ev_product",
                source_id="source_product",
                source_type="prd",
                file_type="txt",
                evidence_type="product_document",
                corpus_type="product_evidence",
                allowed_usage="factual_evidence",
                evidence_strength="medium",
                summary="产品当前版本支持数据集管理。",
                tags=["data"],
            )
        ]
        state.workflow_status = WorkflowStatus.EVIDENCE_MAPPED
        state.next_action = NextAction.DIAGNOSE_SOFTWARE_TYPE
        self.store.save_state(state)
        return state


class FakeHumanGate:
    def __init__(self, store: StateStore) -> None:
        self.store = store
        self.confirmed_decision: TemplateConfirmationDecision | None = None

    def prepare_confirmation(self, run_id: str):
        state = self.store.load_state(run_id)
        state.human_confirmations.append(
            HumanConfirmation(
                confirmation_type=ConfirmationType.TEMPLATE_STRATEGY,
                prompt="确认模板",
                options=["accept_recommendation"],
            )
        )
        state.workflow_status = WorkflowStatus.USER_CONFIRM_REQUIRED
        state.next_action = NextAction.ASK_HUMAN_CONFIRMATION
        self.store.save_state(state)
        return state

    def confirm_template_strategy(
        self,
        run_id: str,
        decision: TemplateConfirmationDecision,
    ):
        self.confirmed_decision = decision
        state = self.store.load_state(run_id)
        pending = state.human_confirmations[0]
        pending.status = ConfirmationStatus.CONFIRMED
        pending.metadata["decision"] = decision.model_dump(mode="json")
        state.workflow_status = WorkflowStatus.USER_CONFIRMED
        state.next_action = NextAction.FREEZE_DOC_PLAN
        self.store.save_state(state)
        return state


class FakeFrozenPlanService:
    def __init__(self, store: StateStore) -> None:
        self.store = store

    def freeze_confirmed_plan(self, run_id: str):
        state = self.store.load_state(run_id)
        state.frozen_doc_plan = FrozenDocPlan(
            project_id=state.project_id,
            locked_status="locked",
            locked_by="human",
            chapter_policy={"locked_top_level_chapters": ["引言"]},
        )
        state.workflow_status = WorkflowStatus.PLAN_FROZEN
        state.next_action = NextAction.CREATE_OUTLINE
        self.store.save_state(state)
        return state


class BadService:
    def __init__(self, store: StateStore) -> None:
        self.store = store

    def write_v1_draft(self, run_id: str):
        state = self.store.load_state(run_id)
        state.workflow_status = WorkflowStatus.DRAFT_V1_CREATED
        state.next_action = NextAction.PLAN_FIGURE_SLOTS
        state.current_draft_version = "v1"
        self.store.save_state(state)
        return state


class MutatingService:
    def __init__(self, store: StateStore, target: Path) -> None:
        self.store = store
        self.target = target

    def plan_figure_slots(self, run_id: str):
        self.target.write_text("mutated", encoding="utf-8")
        state = self.store.load_state(run_id)
        state.figure_slots_ref = "drafts/figure_slots_v1.json"
        (self.target.parent / "figure_slots_v1.json").write_text("{}", encoding="utf-8")
        state.workflow_status = WorkflowStatus.FIGURE_SLOTS_PLANNED
        state.next_action = NextAction.AUDIT_DRAFT
        self.store.save_state(state)
        return state


class DeletingService:
    def __init__(self, store: StateStore, target: Path) -> None:
        self.store = store
        self.target = target

    def plan_figure_slots(self, run_id: str):
        self.target.unlink()
        state = self.store.load_state(run_id)
        state.figure_slots_ref = "drafts/figure_slots_v1.json"
        (self.target.parent / "figure_slots_v1.json").write_text("{}", encoding="utf-8")
        state.workflow_status = WorkflowStatus.FIGURE_SLOTS_PLANNED
        state.next_action = NextAction.AUDIT_DRAFT
        self.store.save_state(state)
        return state


class ExceptionCreatingService:
    def __init__(self, store: StateStore, target: Path) -> None:
        self.store = store
        self.target = target

    def write_v1_draft(self, run_id: str):
        self.target.parent.mkdir(parents=True, exist_ok=True)
        self.target.write_text("new artifact", encoding="utf-8")
        raise RuntimeError("handler exploded")


class WrongStateCreatingService:
    def __init__(self, store: StateStore, target: Path) -> None:
        self.store = store
        self.target = target

    def write_v1_draft(self, run_id: str):
        self.target.parent.mkdir(parents=True, exist_ok=True)
        self.target.write_text("new artifact", encoding="utf-8")
        state = self.store.load_state(run_id)
        state.workflow_status = WorkflowStatus.DRAFT_V2_CREATED
        state.next_action = NextAction.AUDIT_REVISED_DRAFT
        state.current_draft_version = "v2"
        self.store.save_state(state)
        return state


class GoodWriterService:
    def __init__(self, store: StateStore, target: Path) -> None:
        self.store = store
        self.target = target

    def write_v1_draft(self, run_id: str):
        self.target.parent.mkdir(parents=True, exist_ok=True)
        self.target.write_text("draft v1", encoding="utf-8")
        state = self.store.load_state(run_id)
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


class ArtifactWritingFrozenPlanService:
    def __init__(self, store: StateStore, target: Path) -> None:
        self.store = store
        self.target = target

    def freeze_confirmed_plan(self, run_id: str):
        self.target.parent.mkdir(parents=True, exist_ok=True)
        self.target.write_text("partial plan artifact", encoding="utf-8")
        raise RuntimeError("freeze failed after artifact")


def _store(tmp_path: Path) -> tuple[StateStore, str]:
    store = StateStore(data_dir=tmp_path)
    state = store.create_initial_state()
    return store, state.run_id


def _save_status(
    store: StateStore,
    run_id: str,
    status: WorkflowStatus,
    action: NextAction,
) -> None:
    state = store.load_state(run_id)
    state.workflow_status = status
    state.next_action = action
    store.save_state(state)


def test_run_next_step_maps_parse_sources_to_existing_service(tmp_path: Path) -> None:
    store, run_id = _store(tmp_path)
    _save_status(store, run_id, WorkflowStatus.MATERIAL_UPLOADED, NextAction.PARSE_SOURCES)
    parse_service = FakeParseService(store)
    orchestrator = WorkflowOrchestratorService(
        store,
        WorkflowServiceRegistry(source_parsing_service=parse_service),
    )

    summary = orchestrator.run_next_step(run_id)

    assert summary.success is True
    assert summary.executed_steps == 1
    assert summary.workflow_status == WorkflowStatus.SOURCE_PARSED.value
    assert summary.next_action == NextAction.ANALYZE_REFERENCE_STYLE.value
    assert parse_service.calls == 1


def test_source_parsed_analyze_reference_style_routes_to_evidence(tmp_path: Path) -> None:
    store, run_id = _store(tmp_path)
    _save_status(
        store,
        run_id,
        WorkflowStatus.SOURCE_PARSED,
        NextAction.ANALYZE_REFERENCE_STYLE,
    )
    orchestrator = WorkflowOrchestratorService(
        store,
        WorkflowServiceRegistry(evidence_service=FakeEvidenceService(store)),
    )

    summary = orchestrator.run_next_step(run_id)

    assert summary.success is True
    assert summary.last_step is not None
    assert summary.last_step.action == NextAction.EXTRACT_EVIDENCE.value
    assert summary.workflow_status == WorkflowStatus.EVIDENCE_MAPPED.value
    assert summary.next_action == NextAction.DIAGNOSE_SOFTWARE_TYPE.value


def test_run_until_human_confirmation_executes_prepare_then_stops(tmp_path: Path) -> None:
    store, run_id = _store(tmp_path)
    state = store.load_state(run_id)
    state.workflow_status = WorkflowStatus.TEMPLATE_RECOMMENDED
    state.next_action = NextAction.ASK_HUMAN_CONFIRMATION
    state.diagnosis_result = DiagnosisResult(primary_type="Web/SaaS 平台")
    state.template_strategy = TemplateStrategy(
        base_template_id="TEMPLATE_WEB",
        base_template_name="Web 模板",
        recommended_chapters=["引言"],
    )
    store.save_state(state)
    orchestrator = WorkflowOrchestratorService(
        store,
        WorkflowServiceRegistry(human_confirm_gate=FakeHumanGate(store)),
    )

    summary = orchestrator.run_until_human_confirmation_required(run_id)

    assert summary.success is True
    assert summary.waiting_for_human_confirmation is True
    assert summary.executed_steps == 1
    reloaded = store.load_state(run_id)
    assert reloaded.workflow_status == WorkflowStatus.USER_CONFIRM_REQUIRED
    assert reloaded.next_action == NextAction.ASK_HUMAN_CONFIRMATION
    assert reloaded.human_confirmations[0].status == ConfirmationStatus.PENDING


def test_submit_human_confirmation_requires_user_confirm_required(tmp_path: Path) -> None:
    store, run_id = _store(tmp_path)
    _save_status(
        store,
        run_id,
        WorkflowStatus.TEMPLATE_RECOMMENDED,
        NextAction.ASK_HUMAN_CONFIRMATION,
    )
    orchestrator = WorkflowOrchestratorService(
        store,
        WorkflowServiceRegistry(
            human_confirm_gate=FakeHumanGate(store),
            frozen_doc_plan_service=FakeFrozenPlanService(store),
        ),
    )
    decision = TemplateConfirmationDecision(
        selected_base_template_id="TEMPLATE_WEB",
        selected_base_template_name="Web 模板",
        selected_top_level_chapters=["引言"],
    )

    summary = orchestrator.submit_human_confirmation(run_id, decision)

    assert summary.success is False
    assert "不允许提交模板确认" in (summary.error or "")
    assert store.load_state(run_id).workflow_status == WorkflowStatus.TEMPLATE_RECOMMENDED


def test_submit_human_confirmation_freezes_plan_without_auto_default(
    tmp_path: Path,
) -> None:
    store, run_id = _store(tmp_path)
    state = store.load_state(run_id)
    state.workflow_status = WorkflowStatus.USER_CONFIRM_REQUIRED
    state.next_action = NextAction.ASK_HUMAN_CONFIRMATION
    state.human_confirmations.append(
        HumanConfirmation(
            confirmation_type=ConfirmationType.TEMPLATE_STRATEGY,
            prompt="确认模板",
            options=["accept_recommendation"],
        )
    )
    store.save_state(state)
    gate = FakeHumanGate(store)
    orchestrator = WorkflowOrchestratorService(
        store,
        WorkflowServiceRegistry(
            human_confirm_gate=gate,
            frozen_doc_plan_service=FakeFrozenPlanService(store),
        ),
    )
    decision = TemplateConfirmationDecision(
        accepted_recommendation=False,
        selected_base_template_id="CUSTOM_TEMPLATE",
        selected_base_template_name="人工模板",
        selected_top_level_chapters=["人工章节"],
    )

    summary = orchestrator.submit_human_confirmation(run_id, decision)

    assert summary.success is True
    assert summary.workflow_status == WorkflowStatus.PLAN_FROZEN.value
    assert gate.confirmed_decision is not None
    assert gate.confirmed_decision.accepted_recommendation is False
    assert gate.confirmed_decision.selected_base_template_id == "CUSTOM_TEMPLATE"


def test_unsupported_action_does_not_advance_state(tmp_path: Path) -> None:
    store, run_id = _store(tmp_path)
    _save_status(store, run_id, WorkflowStatus.CREATED, NextAction.INGEST_MATERIALS)
    orchestrator = WorkflowOrchestratorService(store, WorkflowServiceRegistry())

    summary = orchestrator.run_next_step(run_id)

    assert summary.success is False
    assert summary.error == "unsupported next_action: ingest_materials"
    assert store.load_state(run_id).workflow_status == WorkflowStatus.CREATED


def test_post_guard_fail_closed_rolls_back_state(tmp_path: Path) -> None:
    store, run_id = _store(tmp_path)
    _save_status(store, run_id, WorkflowStatus.PLAN_GATE_PASSED, NextAction.WRITE_DRAFT)
    orchestrator = WorkflowOrchestratorService(
        store,
        WorkflowServiceRegistry(writer_agent=BadService(store)),
    )

    summary = orchestrator.run_next_step(run_id)

    assert summary.success is False
    assert "预期产物文件不存在" in (summary.error or "")
    reloaded = store.load_state(run_id)
    assert reloaded.workflow_status == WorkflowStatus.PLAN_GATE_PASSED
    assert reloaded.next_action == NextAction.WRITE_DRAFT


def test_pre_guard_rejects_state_artifact_mismatch(tmp_path: Path) -> None:
    store, run_id = _store(tmp_path)
    state = store.load_state(run_id)
    state.workflow_status = WorkflowStatus.DRAFT_V1_CREATED
    state.next_action = NextAction.PLAN_FIGURE_SLOTS
    state.figure_slots_ref = "drafts/figure_slots_v1.json"
    store.save_state(state)
    orchestrator = WorkflowOrchestratorService(
        store,
        WorkflowServiceRegistry(),
    )

    summary = orchestrator.run_next_step(run_id)

    assert summary.success is False
    assert "state 指向的产物不存在" in (summary.error or "")


def test_pre_guard_rejects_stale_evidence_map(tmp_path: Path) -> None:
    store, run_id = _store(tmp_path)
    _save_status(
        store,
        run_id,
        WorkflowStatus.SOURCE_PARSED,
        NextAction.ANALYZE_REFERENCE_STYLE,
    )
    run_dir = get_run_dir(run_id, store.data_dir)
    evidence_path = run_dir / "evidence" / "evidence_map.json"
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    evidence_path.write_text("[]\n", encoding="utf-8")
    orchestrator = WorkflowOrchestratorService(
        store,
        WorkflowServiceRegistry(evidence_service=FakeEvidenceService(store)),
    )

    summary = orchestrator.run_next_step(run_id)

    assert summary.success is False
    assert "stale evidence_map.json" in (summary.error or "")


def test_post_guard_restores_overwritten_existing_business_artifact(
    tmp_path: Path,
) -> None:
    store, run_id = _store(tmp_path)
    state = store.load_state(run_id)
    state.workflow_status = WorkflowStatus.DRAFT_V1_CREATED
    state.next_action = NextAction.PLAN_FIGURE_SLOTS
    state.draft_versions.append(
        DraftVersion(
            draft_id="draft_v1",
            version_label=DraftVersionLabel.V1,
            based_on_plan_id="plan",
            based_on_outline_id="outline",
            content_ref="drafts/draft_v1.json",
        )
    )
    run_dir = get_run_dir(run_id, store.data_dir)
    draft_path = run_dir / "drafts" / "draft_v1.json"
    draft_path.parent.mkdir(parents=True, exist_ok=True)
    draft_path.write_text("original", encoding="utf-8")
    store.save_state(state)
    orchestrator = WorkflowOrchestratorService(
        store,
        WorkflowServiceRegistry(
            figure_slot_planner=MutatingService(store, draft_path),
        ),
    )

    summary = orchestrator.run_next_step(run_id)

    assert summary.success is False
    assert "已有产物被改写" in (summary.error or "")
    assert draft_path.read_text(encoding="utf-8") == "original"
    assert not (draft_path.parent / "figure_slots_v1.json").exists()
    reloaded = store.load_state(run_id)
    assert reloaded.workflow_status == WorkflowStatus.DRAFT_V1_CREATED
    assert reloaded.next_action == NextAction.PLAN_FIGURE_SLOTS


def test_post_guard_restores_deleted_existing_business_artifact(tmp_path: Path) -> None:
    store, run_id = _store(tmp_path)
    state = store.load_state(run_id)
    state.workflow_status = WorkflowStatus.DRAFT_V1_CREATED
    state.next_action = NextAction.PLAN_FIGURE_SLOTS
    state.draft_versions.append(
        DraftVersion(
            draft_id="draft_v1",
            version_label=DraftVersionLabel.V1,
            based_on_plan_id="plan",
            based_on_outline_id="outline",
            content_ref="drafts/draft_v1.json",
        )
    )
    run_dir = get_run_dir(run_id, store.data_dir)
    draft_path = run_dir / "drafts" / "draft_v1.json"
    draft_path.parent.mkdir(parents=True, exist_ok=True)
    draft_path.write_text("original", encoding="utf-8")
    store.save_state(state)
    orchestrator = WorkflowOrchestratorService(
        store,
        WorkflowServiceRegistry(
            figure_slot_planner=DeletingService(store, draft_path),
        ),
    )

    summary = orchestrator.run_next_step(run_id)

    assert summary.success is False
    assert "state 指向的产物不存在" in (summary.error or "")
    assert draft_path.read_text(encoding="utf-8") == "original"
    assert not (draft_path.parent / "figure_slots_v1.json").exists()
    reloaded = store.load_state(run_id)
    assert reloaded.workflow_status == WorkflowStatus.DRAFT_V1_CREATED
    assert reloaded.next_action == NextAction.PLAN_FIGURE_SLOTS


def test_handler_exception_removes_new_business_artifact(tmp_path: Path) -> None:
    store, run_id = _store(tmp_path)
    _save_status(store, run_id, WorkflowStatus.PLAN_GATE_PASSED, NextAction.WRITE_DRAFT)
    run_dir = get_run_dir(run_id, store.data_dir)
    new_path = run_dir / "drafts" / "nested" / "draft_v2.json"
    orchestrator = WorkflowOrchestratorService(
        store,
        WorkflowServiceRegistry(writer_agent=ExceptionCreatingService(store, new_path)),
    )

    summary = orchestrator.run_next_step(run_id)

    assert summary.success is False
    assert "handler exploded" in (summary.error or "")
    assert not new_path.exists()
    assert not new_path.parent.exists()
    reloaded = store.load_state(run_id)
    assert reloaded.workflow_status == WorkflowStatus.PLAN_GATE_PASSED
    assert reloaded.next_action == NextAction.WRITE_DRAFT


def test_post_guard_failure_removes_new_business_artifact(tmp_path: Path) -> None:
    store, run_id = _store(tmp_path)
    _save_status(store, run_id, WorkflowStatus.PLAN_GATE_PASSED, NextAction.WRITE_DRAFT)
    run_dir = get_run_dir(run_id, store.data_dir)
    new_path = run_dir / "drafts" / "draft_v2.json"
    orchestrator = WorkflowOrchestratorService(
        store,
        WorkflowServiceRegistry(writer_agent=WrongStateCreatingService(store, new_path)),
    )

    summary = orchestrator.run_next_step(run_id)

    assert summary.success is False
    assert "后置状态校验失败" in (summary.error or "")
    assert not new_path.exists()
    reloaded = store.load_state(run_id)
    assert reloaded.workflow_status == WorkflowStatus.PLAN_GATE_PASSED
    assert reloaded.next_action == NextAction.WRITE_DRAFT


def test_successful_step_keeps_expected_new_artifact(tmp_path: Path) -> None:
    store, run_id = _store(tmp_path)
    _save_status(store, run_id, WorkflowStatus.PLAN_GATE_PASSED, NextAction.WRITE_DRAFT)
    run_dir = get_run_dir(run_id, store.data_dir)
    draft_path = run_dir / "drafts" / "draft_v1.json"
    orchestrator = WorkflowOrchestratorService(
        store,
        WorkflowServiceRegistry(writer_agent=GoodWriterService(store, draft_path)),
    )

    summary = orchestrator.run_next_step(run_id)

    assert summary.success is True
    assert draft_path.read_text(encoding="utf-8") == "draft v1"
    reloaded = store.load_state(run_id)
    assert reloaded.workflow_status == WorkflowStatus.DRAFT_V1_CREATED
    assert reloaded.next_action == NextAction.PLAN_FIGURE_SLOTS
    assert reloaded.draft_versions[0].content_ref == "drafts/draft_v1.json"


def test_submit_human_confirmation_failure_restores_artifacts(tmp_path: Path) -> None:
    store, run_id = _store(tmp_path)
    state = store.load_state(run_id)
    state.workflow_status = WorkflowStatus.USER_CONFIRM_REQUIRED
    state.next_action = NextAction.ASK_HUMAN_CONFIRMATION
    state.human_confirmations.append(
        HumanConfirmation(
            confirmation_type=ConfirmationType.TEMPLATE_STRATEGY,
            prompt="确认模板",
            options=["accept_recommendation"],
        )
    )
    store.save_state(state)
    run_dir = get_run_dir(run_id, store.data_dir)
    partial_path = run_dir / "drafts" / "partial_freeze.json"
    orchestrator = WorkflowOrchestratorService(
        store,
        WorkflowServiceRegistry(
            human_confirm_gate=FakeHumanGate(store),
            frozen_doc_plan_service=ArtifactWritingFrozenPlanService(store, partial_path),
        ),
    )
    decision = TemplateConfirmationDecision(
        selected_base_template_id="TEMPLATE_WEB",
        selected_base_template_name="Web 模板",
        selected_top_level_chapters=["引言"],
    )

    summary = orchestrator.submit_human_confirmation(run_id, decision)

    assert summary.success is False
    assert "freeze failed after artifact" in (summary.error or "")
    assert not partial_path.exists()
    reloaded = store.load_state(run_id)
    assert reloaded.workflow_status == WorkflowStatus.USER_CONFIRM_REQUIRED
    assert reloaded.next_action == NextAction.ASK_HUMAN_CONFIRMATION
    assert reloaded.human_confirmations[0].status == ConfirmationStatus.PENDING


def test_artifact_restore_failure_is_reported(tmp_path: Path, monkeypatch) -> None:
    store, run_id = _store(tmp_path)
    _save_status(store, run_id, WorkflowStatus.PLAN_GATE_PASSED, NextAction.WRITE_DRAFT)
    run_dir = get_run_dir(run_id, store.data_dir)
    new_path = run_dir / "drafts" / "draft_v2.json"
    orchestrator = WorkflowOrchestratorService(
        store,
        WorkflowServiceRegistry(writer_agent=ExceptionCreatingService(store, new_path)),
    )

    def fail_restore(_run_id, _snapshot):
        raise RuntimeError("restore exploded")

    monkeypatch.setattr(orchestrator, "_restore_business_artifacts", fail_restore)

    summary = orchestrator.run_next_step(run_id)

    assert summary.success is False
    assert "handler exploded" in (summary.error or "")
    assert "restore exploded" in (summary.error or "")
    reloaded = store.load_state(run_id)
    assert reloaded.workflow_status == WorkflowStatus.PLAN_GATE_PASSED
    assert reloaded.next_action == NextAction.WRITE_DRAFT


def test_terminal_summary_exposes_docx_path(tmp_path: Path) -> None:
    store, run_id = _store(tmp_path)
    run_dir = get_run_dir(run_id, store.data_dir)
    docx_path = run_dir / "exports" / "final.docx"
    docx_path.parent.mkdir(parents=True, exist_ok=True)
    docx_path.write_bytes(b"docx")
    state = store.load_state(run_id)
    state.workflow_status = WorkflowStatus.FINAL_EXPORTED
    state.next_action = NextAction.STOP
    state.export_result = ExportResult(
        export_type=ExportType.FINAL,
        docx_path="exports/final.docx",
    )
    state.final_doc_path = "exports/final.docx"
    store.save_state(state)
    orchestrator = WorkflowOrchestratorService(store, WorkflowServiceRegistry())

    summary = orchestrator.resume(run_id)

    assert summary.success is True
    assert summary.terminal is True
    assert summary.docx_path == "exports/final.docx"


def test_waiting_human_confirmation_is_idempotent(tmp_path: Path) -> None:
    store, run_id = _store(tmp_path)
    state = store.load_state(run_id)
    state.workflow_status = WorkflowStatus.USER_CONFIRM_REQUIRED
    state.next_action = NextAction.ASK_HUMAN_CONFIRMATION
    store.save_state(state)
    orchestrator = WorkflowOrchestratorService(
        store,
        WorkflowServiceRegistry(human_confirm_gate=FakeHumanGate(store)),
    )

    summary = orchestrator.run_next_step(run_id)

    assert summary.success is True
    assert summary.executed_steps == 0
    assert summary.waiting_for_human_confirmation is True
    assert store.load_state(run_id).workflow_status == WorkflowStatus.USER_CONFIRM_REQUIRED


def test_orchestrator_does_not_create_external_providers_or_write_business_artifacts() -> None:
    source = Path("docforge_core/workflow/orchestrator.py").read_text(encoding="utf-8")

    assert "create_llm_provider" not in source
    assert "create_embedding_provider" not in source
    assert "QdrantStore" not in source
    assert "get_drafts_dir" not in source
    assert "get_exports_dir" not in source
    assert "get_evidence_dir" not in source
    assert ".write_text(" not in source
