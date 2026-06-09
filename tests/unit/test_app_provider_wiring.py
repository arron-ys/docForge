from typing import Any

import app.main as app_main
from docforge_core.domain.enums import WorkflowStatus
from docforge_core.domain.schemas import DiagnosisResult, TemplateStrategy
from docforge_core.io.state_store import StateStore
from docforge_core.workflow import WorkflowOrchestratorService


def test_create_outline_with_ui_provider_passes_llm_provider(monkeypatch) -> None:
    provider = object()
    captured = {}

    class FakeOutlineAgent:
        def __init__(self, store, llm_provider=None):
            captured["store"] = store
            captured["llm_provider"] = llm_provider

        def create_outline(self, run_id: str):
            captured["run_id"] = run_id
            return "outlined"

    monkeypatch.setattr(app_main, "_create_ui_llm_provider", lambda: provider)
    monkeypatch.setattr(app_main, "OutlineAgent", FakeOutlineAgent)

    store: Any = "store"
    assert app_main._create_outline_with_ui_provider(store, "run_1") == "outlined"
    assert captured == {
        "store": "store",
        "llm_provider": provider,
        "run_id": "run_1",
    }


def test_run_plan_quality_gate_with_ui_provider_passes_llm_provider(monkeypatch) -> None:
    provider = object()
    captured = {}

    class FakePlanQualityGate:
        def __init__(self, store, llm_provider=None):
            captured["store"] = store
            captured["llm_provider"] = llm_provider

        def run(self, run_id: str):
            captured["run_id"] = run_id
            return "gate"

    monkeypatch.setattr(app_main, "_create_ui_llm_provider", lambda: provider)
    monkeypatch.setattr(app_main, "PlanQualityGate", FakePlanQualityGate)

    store: Any = "store"
    assert app_main._run_plan_quality_gate_with_ui_provider(store, "run_1") == "gate"
    assert captured == {
        "store": "store",
        "llm_provider": provider,
        "run_id": "run_1",
    }


def test_write_v1_draft_with_ui_provider_passes_llm_provider(monkeypatch) -> None:
    provider = object()
    captured = {}

    class FakeWriterAgent:
        def __init__(self, store, llm_provider=None):
            captured["store"] = store
            captured["llm_provider"] = llm_provider

        def write_v1_draft(self, run_id: str):
            captured["run_id"] = run_id
            return "drafted"

    monkeypatch.setattr(app_main, "_create_ui_llm_provider", lambda: provider)
    monkeypatch.setattr(app_main, "WriterAgent", FakeWriterAgent)

    store: Any = "store"
    assert app_main._write_v1_draft_with_ui_provider(store, "run_1") == "drafted"
    assert captured == {
        "store": "store",
        "llm_provider": provider,
        "run_id": "run_1",
    }


def test_build_workflow_orchestrator_returns_orchestrator(tmp_path) -> None:
    store = StateStore(data_dir=tmp_path)

    orchestrator = app_main._build_workflow_orchestrator(store)

    assert isinstance(orchestrator, WorkflowOrchestratorService)
    assert orchestrator.state_store is store
    assert orchestrator.services.human_confirm_gate is not None
    assert orchestrator.services.frozen_doc_plan_service is not None
    assert orchestrator.services.docx_export_service is not None


def test_lazy_workflow_services_do_not_create_provider_until_called(monkeypatch) -> None:
    calls = {"provider": 0}
    captured = {}

    class FakeWriterAgent:
        def __init__(self, store, llm_provider=None):
            captured["store"] = store
            captured["llm_provider"] = llm_provider

        def write_v1_draft(self, run_id: str):
            captured["run_id"] = run_id
            return "drafted"

    def fake_provider():
        calls["provider"] += 1
        return "provider"

    monkeypatch.setattr(app_main, "_create_ui_llm_provider", fake_provider)
    monkeypatch.setattr(app_main, "WriterAgent", FakeWriterAgent)

    lazy = app_main._LazyWriterAgent(lambda: app_main.WriterAgent("store", fake_provider()))
    assert calls["provider"] == 0

    assert lazy.write_v1_draft("run_1") == "drafted"

    assert calls["provider"] == 1
    assert captured == {
        "store": "store",
        "llm_provider": "provider",
        "run_id": "run_1",
    }


def test_build_template_confirmation_decision_uses_state_strategy(tmp_path) -> None:
    store = StateStore(data_dir=tmp_path)
    state = store.create_initial_state()
    state.workflow_status = WorkflowStatus.USER_CONFIRM_REQUIRED
    state.diagnosis_result = DiagnosisResult(primary_type="Web/SaaS 平台")
    state.template_strategy = TemplateStrategy(
        base_template_id="TEMPLATE_WEB",
        base_template_name="Web 模板",
        enhancement_pack_ids=["PACK_DATA"],
        recommended_chapters=["引言", "核心功能"],
        risk_chapters=["AI 能力待确认"],
    )
    store.save_state(state)

    decision = app_main._build_template_confirmation_decision(
        store,
        state.run_id,
        risk_acknowledged=True,
    )

    assert decision.selected_base_template_id == "TEMPLATE_WEB"
    assert decision.selected_top_level_chapters == ["引言", "核心功能"]
    assert decision.risk_acknowledged is True
    assert decision.acknowledged_risk_chapters == ["AI 能力待确认"]


def test_streamlit_main_uses_orchestrator_panel_and_collapsed_debug() -> None:
    source = app_main.Path("app/main.py").read_text(encoding="utf-8")

    assert "_render_workflow_panel(store, run_id)" in source
    assert 'st.expander("开发调试入口", expanded=False)' in source
    assert "_render_state_table(store, run_id)" in source


def test_workflow_panel_terminal_download_only_uses_docx() -> None:
    source = app_main.Path("app/main.py").read_text(encoding="utf-8")
    panel = source.split("def _render_workflow_panel", 1)[1].split(
        "def _run_workflow_action",
        1,
    )[0]

    assert "_render_docx_download" in panel
    assert "manifest" not in panel.lower()
    assert "audit" not in panel.lower()
    assert "evidence" not in panel.lower()
    assert "state.json" not in panel
