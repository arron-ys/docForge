from __future__ import annotations

import os
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.deps import get_state_store
from api.main import app
from docforge_core.domain.enums import (
    AllowedUsage,
    CorpusType,
    ExportType,
    FileType,
    NextAction,
    ParseStatus,
    SourceType,
    WorkflowStatus,
)
from docforge_core.domain.schemas import ExportResult, SourceItem
from docforge_core.io.run_paths import get_exports_dir
from docforge_core.io.state_store import StateStore


@pytest.fixture()
def api_client(tmp_path: Path) -> Generator[tuple[TestClient, StateStore]]:
    store = StateStore(data_dir=tmp_path)
    app.dependency_overrides[get_state_store] = lambda: store
    try:
        yield TestClient(app), store
    finally:
        app.dependency_overrides.clear()


def test_workspace_view_returns_user_readable_state_without_raw_state(
    api_client: tuple[TestClient, StateStore],
) -> None:
    client, store = api_client
    state = store.create_initial_state(project_name="DataTalk")
    state.workflow_status = WorkflowStatus.MATERIAL_UPLOADED
    state.next_action = NextAction.PARSE_SOURCES
    store.save_state(state)

    response = client.get(f"/api/workspace/{state.run_id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["run_summary"]["stage_label"] == "资料已上传，等待解析"
    assert payload["primary_action"]["action_type"] == "parse_sources"
    assert "workflow_status" not in payload
    assert "qdrant_collection" not in payload
    assert "source_registry" not in payload


def test_list_runs_returns_existing_runs_newest_first(
    api_client: tuple[TestClient, StateStore],
) -> None:
    client, store = api_client
    first = store.create_initial_state(project_name="First")
    second = store.create_initial_state(project_name="Second")

    first_state_file = store.data_dir / "runs" / first.run_id / "state.json"
    second_state_file = store.data_dir / "runs" / second.run_id / "state.json"
    os.utime(first_state_file, (1_700_000_000, 1_700_000_000))
    os.utime(second_state_file, (1_700_000_100, 1_700_000_100))

    response = client.get("/api/runs")

    assert response.status_code == 200
    runs = response.json()["runs"]
    assert [item["run_id"] for item in runs] == [second.run_id, first.run_id]
    assert runs[0]["project_name"] == "Second"
    assert runs[0]["stage_label"] == "项目已创建，等待上传资料"


def test_create_run_returns_workspace_for_new_task(
    api_client: tuple[TestClient, StateStore],
) -> None:
    client, store = api_client

    response = client.post("/api/runs", json={"project_name": "New Project"})

    assert response.status_code == 200
    payload = response.json()
    run_id = payload["run"]["run_id"]
    assert payload["run"]["project_name"] == "New Project"
    assert payload["workspace"]["run_summary"]["run_id"] == run_id
    assert payload["workspace"]["primary_action"]["action_type"] == "open_upload"
    assert (store.data_dir / "runs" / run_id / "state.json").exists()


def test_upload_reference_generates_reference_style_source(
    api_client: tuple[TestClient, StateStore],
) -> None:
    client, store = api_client
    state = store.create_initial_state()

    response = client.post(
        f"/api/runs/{state.run_id}/sources/reference",
        files={"file": ("reference.pdf", b"PDF", "application/pdf")},
    )

    assert response.status_code == 200
    source = response.json()["source"]
    assert source["corpus_type"] == "reference_style"
    assert source["allowed_usage"] == "style_only"
    assert source["source_type"] == "reference_soft_copyright_doc"
    assert (store.data_dir / "runs" / state.run_id / source["file_path"]).exists()


def test_upload_product_generates_product_evidence_source(
    api_client: tuple[TestClient, StateStore],
) -> None:
    client, store = api_client
    state = store.create_initial_state()

    response = client.post(
        f"/api/runs/{state.run_id}/sources/product",
        files={"file": ("product.docx", b"DOCX", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
    )

    assert response.status_code == 200
    source = response.json()["source"]
    assert source["corpus_type"] == "product_evidence"
    assert source["allowed_usage"] == "factual_evidence"
    assert source["source_type"] == "product_intro_doc"
    assert (store.data_dir / "runs" / state.run_id / source["file_path"]).exists()


def test_upload_screenshot_returns_display_material_only_view(
    api_client: tuple[TestClient, StateStore],
) -> None:
    client, store = api_client
    state = store.create_initial_state()

    response = client.post(
        f"/api/runs/{state.run_id}/sources/screenshots",
        files={"file": ("dashboard.png", b"PNG", "image/png")},
    )

    assert response.status_code == 200
    source = response.json()["source"]
    assert source["corpus_type"] == "product_evidence"
    assert source["allowed_usage"] == "display_material_only"
    assert "不做 OCR" in source["notes"]
    persisted = store.load_state(state.run_id).source_registry[-1]
    assert persisted.allowed_usage == AllowedUsage.DISPLAY_MATERIAL_ONLY


def test_illegal_action_returns_409_and_does_not_advance(
    api_client: tuple[TestClient, StateStore],
) -> None:
    client, store = api_client
    state = store.create_initial_state()

    response = client.post(f"/api/runs/{state.run_id}/actions/export-risk-docx")

    assert response.status_code == 409
    assert response.json()["error_code"] == "action_not_allowed"
    loaded = store.load_state(state.run_id)
    assert loaded.workflow_status == WorkflowStatus.CREATED
    assert loaded.next_action == NextAction.INGEST_MATERIALS


def test_artifact_download_rejects_path_traversal(
    api_client: tuple[TestClient, StateStore],
) -> None:
    client, store = api_client
    state = store.create_initial_state()
    state.workflow_status = WorkflowStatus.FINAL_EXPORTED
    state.next_action = NextAction.STOP
    state.export_result = ExportResult(
        export_type=ExportType.FINAL,
        docx_path="../../secret.docx",
    )
    store.save_state(state)

    response = client.get(f"/api/artifacts/{state.run_id}:final_docx/download")

    assert response.status_code == 400
    assert response.json()["error_code"] == "artifact_path_invalid"


def test_artifact_not_found_returns_404(api_client: tuple[TestClient, StateStore]) -> None:
    client, store = api_client
    state = store.create_initial_state()

    response = client.get(f"/api/artifacts/{state.run_id}:final_docx/download")

    assert response.status_code == 404
    assert response.json()["error_code"] == "artifact_not_found"


def test_diagnostics_api_uses_existing_diagnostics_service(
    api_client: tuple[TestClient, StateStore],
) -> None:
    client, store = api_client
    state = store.create_initial_state()

    response = client.get(f"/api/runs/{state.run_id}/diagnostics")

    assert response.status_code == 200
    payload = response.json()
    assert payload["stage_label"] == "项目已创建，等待上传资料"
    assert "health_label" in payload
    assert "severity_counts" in payload


@pytest.mark.parametrize(
    "path",
    [
        "/api/workspace/bad-run-id",
        "/api/runs/bad-run-id/diagnostics",
    ],
)
def test_invalid_run_id_get_endpoints_return_400(
    api_client: tuple[TestClient, StateStore],
    path: str,
) -> None:
    client, _store = api_client

    response = client.get(path)

    assert response.status_code == 400
    assert response.json()["error_code"] == "invalid_run_id"
    assert response.json()["recoverable"] is False


@pytest.mark.parametrize(
    "path",
    [
        "/api/runs/bad-run-id/sources/reference",
        "/api/runs/bad-run-id/sources/product",
        "/api/runs/bad-run-id/sources/screenshots",
    ],
)
def test_invalid_run_id_upload_endpoints_return_400(
    api_client: tuple[TestClient, StateStore],
    path: str,
) -> None:
    client, _store = api_client

    response = client.post(
        path,
        files={"file": ("material.txt", b"text", "text/plain")},
    )

    assert response.status_code == 400
    assert response.json()["error_code"] == "invalid_run_id"
    assert response.json()["recoverable"] is False


def test_invalid_run_id_notes_endpoint_returns_400(
    api_client: tuple[TestClient, StateStore],
) -> None:
    client, _store = api_client

    response = client.post(
        "/api/runs/bad-run-id/sources/notes",
        json={"content": "用户补充说明"},
    )

    assert response.status_code == 400
    assert response.json()["error_code"] == "invalid_run_id"
    assert response.json()["recoverable"] is False


@pytest.mark.parametrize(
    ("path", "payload"),
    [
        ("/api/runs/bad-run-id/actions/next", {}),
        (
            "/api/runs/bad-run-id/actions/confirm-product-type",
            {"selected_product_type": "Web/SaaS 平台"},
        ),
        ("/api/runs/bad-run-id/actions/confirm-doc-plan", {}),
        ("/api/runs/bad-run-id/actions/export-final-docx", {}),
        ("/api/runs/bad-run-id/actions/export-risk-docx", {}),
    ],
)
def test_invalid_run_id_action_endpoints_return_400(
    api_client: tuple[TestClient, StateStore],
    path: str,
    payload: dict[str, str],
) -> None:
    client, _store = api_client

    response = client.post(path, json=payload)

    assert response.status_code == 400
    assert response.json()["error_code"] == "invalid_run_id"
    assert response.json()["recoverable"] is False


def test_workspace_view_hides_internal_source_ids_from_messages(
    api_client: tuple[TestClient, StateStore],
) -> None:
    client, store = api_client
    state = store.create_initial_state()
    state.source_registry.append(
        SourceItem(
            source_id="source_secret",
            source_type=SourceType.PRODUCT_INTRO_DOC,
            file_type=FileType.DOCX,
            corpus_type=CorpusType.PRODUCT_EVIDENCE,
            allowed_usage=AllowedUsage.FACTUAL_EVIDENCE,
            is_product_source=True,
            parse_status=ParseStatus.PENDING,
        )
    )
    store.save_state(state)

    response = client.get(f"/api/workspace/{state.run_id}")

    assert response.status_code == 200
    payload_text = response.text
    assert "qdrant_collection" not in payload_text
    assert "source_registry" not in payload_text


def test_existing_docx_artifact_can_download(api_client: tuple[TestClient, StateStore]) -> None:
    client, store = api_client
    state = store.create_initial_state()
    export_dir = get_exports_dir(state.run_id, store.data_dir)
    docx_path = export_dir / "result.docx"
    docx_path.write_bytes(b"DOCX")
    state.workflow_status = WorkflowStatus.FINAL_EXPORTED
    state.next_action = NextAction.STOP
    state.export_result = ExportResult(
        export_type=ExportType.FINAL,
        docx_path="exports/result.docx",
    )
    store.save_state(state)

    response = client.get(f"/api/artifacts/{state.run_id}:final_docx/download")

    assert response.status_code == 200
    assert response.content == b"DOCX"


def test_artifact_download_rejects_invalid_run_id_in_artifact_id(
    api_client: tuple[TestClient, StateStore],
) -> None:
    client, _store = api_client

    response = client.get("/api/artifacts/bad-run-id:final_docx/download")

    assert response.status_code == 400
    assert response.json()["error_code"] == "invalid_run_id"
    assert response.json()["recoverable"] is False


def test_final_artifact_kind_requires_final_export_type(
    api_client: tuple[TestClient, StateStore],
) -> None:
    client, store = api_client
    state = store.create_initial_state()
    export_dir = get_exports_dir(state.run_id, store.data_dir)
    docx_path = export_dir / "risk.docx"
    docx_path.write_bytes(b"RISK")
    state.workflow_status = WorkflowStatus.RISK_EXPORTED
    state.next_action = NextAction.STOP
    state.export_result = ExportResult(
        export_type=ExportType.RISK,
        docx_path="exports/risk.docx",
    )
    store.save_state(state)

    response = client.get(f"/api/artifacts/{state.run_id}:final_docx/download")

    assert response.status_code == 404
    assert response.json()["error_code"] == "artifact_not_found"


def test_risk_artifact_kind_requires_risk_export_type(
    api_client: tuple[TestClient, StateStore],
) -> None:
    client, store = api_client
    state = store.create_initial_state()
    export_dir = get_exports_dir(state.run_id, store.data_dir)
    docx_path = export_dir / "final.docx"
    docx_path.write_bytes(b"FINAL")
    state.workflow_status = WorkflowStatus.FINAL_EXPORTED
    state.next_action = NextAction.STOP
    state.export_result = ExportResult(
        export_type=ExportType.FINAL,
        docx_path="exports/final.docx",
    )
    store.save_state(state)

    response = client.get(f"/api/artifacts/{state.run_id}:risk_docx/download")

    assert response.status_code == 404
    assert response.json()["error_code"] == "artifact_not_found"


def test_existing_risk_docx_artifact_can_download(
    api_client: tuple[TestClient, StateStore],
) -> None:
    client, store = api_client
    state = store.create_initial_state()
    export_dir = get_exports_dir(state.run_id, store.data_dir)
    docx_path = export_dir / "risk.docx"
    docx_path.write_bytes(b"RISK")
    state.workflow_status = WorkflowStatus.RISK_EXPORTED
    state.next_action = NextAction.STOP
    state.export_result = ExportResult(
        export_type=ExportType.RISK,
        docx_path="exports/risk.docx",
    )
    store.save_state(state)

    response = client.get(f"/api/artifacts/{state.run_id}:risk_docx/download")

    assert response.status_code == 200
    assert response.content == b"RISK"
