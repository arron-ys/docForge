from pathlib import Path

import app.main as app_main
from docforge_core.io.state_store import StateStore


def test_streamlit_sample_project_button_exists() -> None:
    source = app_main.Path("app/main.py").read_text(encoding="utf-8")

    assert "load_e2e_sample_project" in source
    assert "加载本地样例工程" in source
    assert "_render_sample_project_loader(store, run_id)" in source


def test_streamlit_sample_project_loader_imports_sources(tmp_path: Path, monkeypatch) -> None:
    store = StateStore(data_dir=tmp_path)
    state = store.create_initial_state()
    calls = {"rerun": 0}

    class FakeExpander:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

    monkeypatch.setattr(app_main.st, "expander", lambda *args, **kwargs: FakeExpander())
    monkeypatch.setattr(app_main.st, "caption", lambda *args, **kwargs: None)
    monkeypatch.setattr(app_main.st, "button", lambda *args, **kwargs: True)
    monkeypatch.setattr(app_main.st, "success", lambda *args, **kwargs: None)
    monkeypatch.setattr(app_main.st, "info", lambda *args, **kwargs: None)
    monkeypatch.setattr(app_main.st, "exception", lambda exc: (_ for _ in ()).throw(exc))
    monkeypatch.setattr(app_main.st, "dataframe", lambda *args, **kwargs: None)
    monkeypatch.setattr(app_main.st, "rerun", lambda: calls.__setitem__("rerun", 1))

    app_main._render_sample_project_loader(store, state.run_id)

    reloaded = store.load_state(state.run_id)
    assert calls["rerun"] == 1
    assert len(reloaded.source_registry) == 6
    assert reloaded.target_product_name == "墨衡演示数据管理平台"


def test_streamlit_sample_project_does_not_offer_manifest_download() -> None:
    source = app_main.Path("app/main.py").read_text(encoding="utf-8")
    loader = source.split("def _render_sample_project_loader", 1)[1].split(
        "def _create_outline_with_ui_provider",
        1,
    )[0]
    panel = source.split("def _render_workflow_panel", 1)[1].split(
        "def _run_workflow_action",
        1,
    )[0]

    assert "download_button" not in loader
    assert "_render_docx_download" in panel
    assert "manifest" not in panel.lower()
    assert "audit" not in panel.lower()
    assert "state.json" not in panel


def test_streamlit_main_flow_shows_health_status() -> None:
    source = app_main.Path("app/main.py").read_text(encoding="utf-8")

    assert "健康状态" in source
    assert "下一步建议" in source
    assert "workflow_status" in source
    assert "next_action" in source


def test_streamlit_main_flow_uses_diagnostics_service() -> None:
    source = app_main.Path("app/main.py").read_text(encoding="utf-8")

    assert "WorkflowDiagnosticsService" in source
    assert "_render_health_report(health)" in source


def test_streamlit_debug_info_default_collapsed() -> None:
    source = app_main.Path("app/main.py").read_text(encoding="utf-8")

    assert 'st.expander("开发调试入口", expanded=False)' in source
    assert 'st.expander("开发调试信息", expanded=False)' in source


def test_streamlit_terminal_only_offers_docx_download() -> None:
    source = app_main.Path("app/main.py").read_text(encoding="utf-8")
    terminal = source.split("def _render_docx_export", 1)[1].split(
        "def _render_docx_download",
        1,
    )[0]

    assert "_render_docx_download" in terminal
    assert "manifest" not in terminal.lower()
    assert "evidence_map" not in terminal.lower()
    assert "state.json" not in terminal


def test_streamlit_does_not_offer_internal_artifact_downloads() -> None:
    source = app_main.Path("app/main.py").read_text(encoding="utf-8")
    assert "st.download_button" in source
    assert "export_manifest" not in source.split("def _render_docx_download", 1)[1]
    assert "audit_report" not in source.split("def _render_docx_download", 1)[1]
    assert "evidence_map" not in source.split("def _render_docx_download", 1)[1]


def test_streamlit_sample_partial_import_shows_user_error(tmp_path: Path, monkeypatch) -> None:
    store = StateStore(data_dir=tmp_path)
    state = store.create_initial_state()
    errors: list[str] = []

    class FakeExpander:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

    monkeypatch.setattr(app_main.st, "expander", lambda *args, **kwargs: FakeExpander())
    monkeypatch.setattr(app_main.st, "caption", lambda *args, **kwargs: None)
    monkeypatch.setattr(app_main.st, "button", lambda *args, **kwargs: True)
    monkeypatch.setattr(app_main.st, "success", lambda *args, **kwargs: None)
    monkeypatch.setattr(app_main.st, "info", lambda *args, **kwargs: None)
    monkeypatch.setattr(app_main.st, "write", lambda *args, **kwargs: None)
    monkeypatch.setattr(app_main.st, "error", lambda message: errors.append(message))
    monkeypatch.setattr(app_main.st, "dataframe", lambda *args, **kwargs: None)
    monkeypatch.setattr(app_main.st, "rerun", lambda: None)
    monkeypatch.setattr(
        app_main,
        "load_e2e_sample_project",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            ValueError("样例工程处于部分导入状态: ev_secret source_hidden")
        ),
    )

    app_main._render_sample_project_loader(store, state.run_id)

    assert errors
    assert "ev_secret" not in errors[0]
    assert "source_hidden" not in errors[0]
