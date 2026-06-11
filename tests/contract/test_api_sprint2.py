from __future__ import annotations

import os
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.deps import (
    get_runtime_model_config_service_dep,
    get_state_store,
    get_workflow_orchestrator,
)
from api.main import app
from docforge_core.config.runtime_model_config import RuntimeModelConfigService
from docforge_core.domain.enums import (
    AllowedUsage,
    ConfirmationStatus,
    ConfirmationType,
    CorpusType,
    ExportType,
    FileType,
    NextAction,
    ParseStatus,
    SourceType,
    WorkflowStatus,
)
from docforge_core.domain.schemas import (
    DiagnosisResult,
    ExportResult,
    FrozenDocPlan,
    HumanConfirmation,
    SourceItem,
    TemplateConfirmationDecision,
    TemplateStrategy,
)
from docforge_core.io.run_paths import get_exports_dir
from docforge_core.io.state_store import StateStore
from docforge_core.workflow import WorkflowRunSummary
from docforge_core.workflow.wiring import build_workflow_service_registry


class FakeStartOrchestrator:
    def __init__(
        self,
        store: StateStore,
        *,
        success: bool = True,
        error: str | None = None,
    ) -> None:
        self.store = store
        self.success = success
        self.error = error
        self.calls = 0

    def run_until_human_confirmation_required(
        self,
        run_id: str,
        max_steps: int = 30,
    ) -> WorkflowRunSummary:
        self.calls += 1
        state = self.store.load_state(run_id)
        if self.success:
            for source in state.source_registry:
                source.parse_status = ParseStatus.PARSED
            state.workflow_status = WorkflowStatus.SOURCE_PARSED
            state.next_action = NextAction.ANALYZE_REFERENCE_STYLE
            self.store.save_state(state)
            return WorkflowRunSummary(
                run_id=run_id,
                workflow_status=state.workflow_status.value,
                next_action=state.next_action.value,
                description="资料解析已完成",
                next_operation="构建证据",
                success=True,
                terminal=False,
                waiting_for_human_confirmation=False,
                executed_steps=1,
            )
        return WorkflowRunSummary(
            run_id=run_id,
            workflow_status=state.workflow_status.value,
            next_action=state.next_action.value,
            description="启动主流程失败",
            next_operation="修复错误后重试",
            success=False,
            terminal=False,
            waiting_for_human_confirmation=False,
            error=self.error or "启动主流程失败",
        )


class FakeConfirmOrchestrator:
    def __init__(self, store: StateStore) -> None:
        self.store = store
        self.calls = 0
        self.decision: TemplateConfirmationDecision | None = None
        self.confirmation_source = "manual"
        self.confirmation_metadata: dict[str, object] | None = None

    def get_summary(self, run_id: str) -> WorkflowRunSummary:
        state = self.store.load_state(run_id)
        return WorkflowRunSummary(
            run_id=run_id,
            workflow_status=state.workflow_status.value,
            next_action=state.next_action.value,
            description="当前任务状态",
            next_operation="确认策略",
            success=True,
            terminal=False,
            waiting_for_human_confirmation=(
                state.workflow_status == WorkflowStatus.USER_CONFIRM_REQUIRED
            ),
        )

    def submit_human_confirmation(
        self,
        run_id: str,
        decision: TemplateConfirmationDecision,
        *,
        confirmation_source: str = "manual",
        confirmation_metadata: dict[str, object] | None = None,
    ) -> WorkflowRunSummary:
        self.calls += 1
        self.decision = decision
        self.confirmation_source = confirmation_source
        self.confirmation_metadata = confirmation_metadata
        state = self.store.load_state(run_id)
        if confirmation_metadata:
            confirmation = next(
                (
                    item
                    for item in reversed(state.human_confirmations)
                    if item.confirmation_type == ConfirmationType.TEMPLATE_STRATEGY
                ),
                None,
            )
            if confirmation is None:
                confirmation = HumanConfirmation(
                    confirmation_type=ConfirmationType.TEMPLATE_STRATEGY,
                    prompt="确认策略",
                )
                state.human_confirmations.append(confirmation)
            confirmation.status = ConfirmationStatus.CONFIRMED
            confirmation.metadata["confirmation_source"] = confirmation_source
            confirmation.metadata["product_and_doc_strategy_confirmation"] = confirmation_metadata
        state.workflow_status = WorkflowStatus.PLAN_FROZEN
        state.next_action = NextAction.CREATE_OUTLINE
        self.store.save_state(state)
        return WorkflowRunSummary(
            run_id=run_id,
            workflow_status=state.workflow_status.value,
            next_action=state.next_action.value,
            description="模板已确认，FrozenDocPlan 已冻结",
            next_operation="生成文档目录",
            success=True,
            terminal=False,
            waiting_for_human_confirmation=False,
            executed_steps=1,
        )


class FakeAutoConfirmationOrchestrator(FakeConfirmOrchestrator):
    def run_until_human_confirmation_required(
        self,
        run_id: str,
        max_steps: int = 30,
    ) -> WorkflowRunSummary:
        state = self.store.load_state(run_id)
        state.workflow_status = WorkflowStatus.USER_CONFIRM_REQUIRED
        state.next_action = NextAction.ASK_HUMAN_CONFIRMATION
        state.diagnosis_result = DiagnosisResult(
            primary_type="Web/SaaS 平台",
            primary_type_confidence=0.85,
        )
        state.template_strategy = TemplateStrategy(
            base_template_id="TEMPLATE_WEB",
            base_template_name="Web 模板",
            recommended_chapters=["引言", "核心功能说明"],
        )
        state.human_confirmations.append(
            HumanConfirmation(
                confirmation_type=ConfirmationType.TEMPLATE_STRATEGY,
                prompt="确认策略",
            )
        )
        self.store.save_state(state)
        return WorkflowRunSummary(
            run_id=run_id,
            workflow_status=state.workflow_status.value,
            next_action=state.next_action.value,
            description="已到达人工确认点",
            next_operation="确认策略",
            success=True,
            terminal=False,
            waiting_for_human_confirmation=True,
        )


@pytest.fixture()
def api_client(tmp_path: Path) -> Generator[tuple[TestClient, StateStore]]:
    store = StateStore(data_dir=tmp_path)
    model_config_service = RuntimeModelConfigService(tmp_path / "model_config.json")
    app.dependency_overrides[get_state_store] = lambda: store
    app.dependency_overrides[get_runtime_model_config_service_dep] = lambda: model_config_service
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
    assert payload["run_summary"]["stage_label"] == "资料已上传，等待开始"
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


def test_model_config_api_saves_and_returns_masked_keys(
    api_client: tuple[TestClient, StateStore],
) -> None:
    client, _store = api_client

    response = client.post(
        "/api/model-config",
        json={
            "llm": {
                "provider": "qwen",
                "model": "qwen-plus",
                "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
                "api_key": "unit-llm-secret-12345678",
            },
            "embedding": {
                "provider": "jina",
                "model": "jina-embeddings-v3",
                "base_url": "https://api.jina.ai/v1",
                "api_key": "unit-embedding-secret-87654321",
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["llm"]["has_api_key"] is True
    assert payload["llm"]["masked_api_key"] == "unit****5678"
    assert "unit-llm-secret-12345678" not in response.text
    assert payload["embedding"]["masked_api_key"] == "unit****4321"

    get_response = client.get("/api/model-config")

    assert get_response.status_code == 200
    assert "unit-embedding-secret-87654321" not in get_response.text
    assert get_response.json()["embedding"]["has_api_key"] is True


def test_model_config_api_empty_key_preserves_existing_key(
    api_client: tuple[TestClient, StateStore],
) -> None:
    client, _store = api_client
    client.post(
        "/api/model-config",
        json={
            "llm": {
                "provider": "qwen",
                "model": "qwen-plus",
                "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
                "api_key": "unit-existing-llm-secret",
            },
        },
    )

    response = client.post(
        "/api/model-config",
        json={
            "llm": {
                "provider": "qwen",
                "model": "qwen-max",
                "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
                "api_key": "",
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["llm"]["model"] == "qwen-max"
    assert payload["llm"]["has_api_key"] is True
    assert payload["llm"]["masked_api_key"] == "unit****cret"


def test_model_config_test_api_without_key_returns_readable_error(
    api_client: tuple[TestClient, StateStore],
) -> None:
    client, _store = api_client

    response = client.post(
        "/api/model-config/test-llm",
        json={
            "provider": "qwen",
            "model": "qwen-plus",
            "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "api_key": "",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["verified"] is False
    assert payload["error_code"] == "missing_api_key"
    assert "API Key" in payload["message"]


def test_workflow_wiring_includes_source_parsing_service(
    api_client: tuple[TestClient, StateStore],
) -> None:
    _client, store = api_client

    registry = build_workflow_service_registry(store)

    assert registry.source_parsing_service is not None
    assert registry.evidence_service is not None
    assert registry.docx_export_service is not None


def test_start_action_runs_injected_orchestrator_for_product_document(
    api_client: tuple[TestClient, StateStore],
) -> None:
    client, store = api_client
    state = store.create_initial_state()
    store.add_source_item(state.run_id, _api_source_item(SourceType.PRD, FileType.TXT))
    _save_verified_model_config(client)
    fake_orchestrator = FakeStartOrchestrator(store)
    app.dependency_overrides[get_workflow_orchestrator] = lambda: fake_orchestrator

    response = client.post(f"/api/runs/{state.run_id}/actions/start")

    assert response.status_code == 200
    assert fake_orchestrator.calls == 1
    payload = response.json()
    assert payload["workspace"]["run_summary"]["stage_label"] == "资料解析完成，正在分析参考风格和产品内容"
    loaded = store.load_state(state.run_id)
    assert loaded.workflow_status == WorkflowStatus.SOURCE_PARSED
    assert loaded.source_registry[0].parse_status == ParseStatus.PARSED


def test_start_action_requires_model_config(
    api_client: tuple[TestClient, StateStore],
) -> None:
    client, store = api_client
    state = store.create_initial_state()
    store.add_source_item(state.run_id, _api_source_item(SourceType.PRD, FileType.TXT))
    fake_orchestrator = FakeStartOrchestrator(store)
    app.dependency_overrides[get_workflow_orchestrator] = lambda: fake_orchestrator

    response = client.post(f"/api/runs/{state.run_id}/actions/start")

    assert response.status_code == 409
    assert response.json()["error_code"] == "model_config_missing"
    assert fake_orchestrator.calls == 0


def test_start_action_rejects_reference_only(
    api_client: tuple[TestClient, StateStore],
) -> None:
    client, store = api_client
    state = store.create_initial_state()
    store.add_source_item(
        state.run_id,
        _api_source_item(
            SourceType.REFERENCE_SOFT_COPYRIGHT_DOC,
            FileType.TXT,
            is_reference_source=True,
            is_product_source=False,
            allowed_usage=AllowedUsage.STYLE_ONLY,
            corpus_type=CorpusType.REFERENCE_STYLE,
        ),
    )

    response = client.post(f"/api/runs/{state.run_id}/actions/start")

    assert response.status_code == 409
    payload = response.json()
    assert payload["error_code"] == "reference_only_not_allowed"
    assert "外部参考资料不能作为产品事实来源" in payload["message"]


def test_start_action_rejects_screenshot_only(
    api_client: tuple[TestClient, StateStore],
) -> None:
    client, store = api_client
    state = store.create_initial_state()
    store.add_source_item(
        state.run_id,
        _api_source_item(
            SourceType.SCREENSHOT,
            FileType.PNG,
            allowed_usage=AllowedUsage.DISPLAY_MATERIAL_ONLY,
            is_product_source=True,
        ),
    )

    response = client.post(f"/api/runs/{state.run_id}/actions/start")

    assert response.status_code == 409
    payload = response.json()
    assert payload["error_code"] == "screenshot_only_not_allowed"
    assert "不做 OCR" in payload["message"]


def test_start_action_maps_missing_workflow_dependency(
    api_client: tuple[TestClient, StateStore],
) -> None:
    client, store = api_client
    state = store.create_initial_state()
    store.add_source_item(state.run_id, _api_source_item(SourceType.PRD, FileType.TXT))
    _save_verified_model_config(client)
    app.dependency_overrides[get_workflow_orchestrator] = lambda: FakeStartOrchestrator(
        store,
        success=False,
        error="缺少工作流服务依赖: source_parsing_service",
    )

    response = client.post(f"/api/runs/{state.run_id}/actions/start")

    assert response.status_code == 500
    payload = response.json()
    assert payload["error_code"] == "workflow_dependency_missing"
    assert "解析服务未接入" in payload["message"]
    assert "Traceback" not in payload["message"]


def test_start_action_conditionally_auto_confirms_and_records_result(
    api_client: tuple[TestClient, StateStore],
) -> None:
    client, store = api_client
    state = store.create_initial_state()
    store.add_source_item(state.run_id, _api_source_item(SourceType.PRD, FileType.TXT))
    _save_verified_model_config(client)
    fake_orchestrator = FakeAutoConfirmationOrchestrator(store)
    app.dependency_overrides[get_workflow_orchestrator] = lambda: fake_orchestrator

    response = client.post(f"/api/runs/{state.run_id}/actions/start")

    assert response.status_code == 200
    assert fake_orchestrator.calls == 1
    assert fake_orchestrator.confirmation_source == "auto"
    assert "已根据当前资料自动确认产品类型和文档策略" in response.json()["message"]
    payload = response.json()["workspace"]
    assert payload["confirmation_state"]["auto_confirmed"] is True
    assert payload["confirmation_state"]["required"] is False
    assert any(
        "已根据当前资料自动确认产品类型和文档策略" in item["content"]
        for item in payload["messages"]
    )


def test_start_action_resumes_auto_confirmation_after_interruption(
    api_client: tuple[TestClient, StateStore],
) -> None:
    client, store = api_client
    state = store.create_initial_state()
    state.source_registry = [_api_source_item(SourceType.PRD, FileType.TXT)]
    state.workflow_status = WorkflowStatus.USER_CONFIRM_REQUIRED
    state.next_action = NextAction.ASK_HUMAN_CONFIRMATION
    state.diagnosis_result = DiagnosisResult(
        primary_type="Web/SaaS 平台",
        primary_type_confidence=0.85,
    )
    state.template_strategy = TemplateStrategy(
        base_template_id="TEMPLATE_WEB",
        base_template_name="Web 模板",
        recommended_chapters=["引言"],
    )
    state.human_confirmations = [
        HumanConfirmation(
            confirmation_type=ConfirmationType.TEMPLATE_STRATEGY,
            prompt="确认策略",
        )
    ]
    store.save_state(state)
    fake_orchestrator = FakeConfirmOrchestrator(store)
    app.dependency_overrides[get_workflow_orchestrator] = lambda: fake_orchestrator

    response = client.post(f"/api/runs/{state.run_id}/actions/start")

    assert response.status_code == 200
    assert fake_orchestrator.confirmation_source == "auto"
    assert store.load_state(state.run_id).workflow_status == WorkflowStatus.PLAN_FROZEN


def test_confirm_doc_plan_submits_default_recommendation(
    api_client: tuple[TestClient, StateStore],
) -> None:
    client, store = api_client
    state = store.create_initial_state()
    state.workflow_status = WorkflowStatus.USER_CONFIRM_REQUIRED
    state.next_action = NextAction.ASK_HUMAN_CONFIRMATION
    state.diagnosis_result = DiagnosisResult(primary_type="通用软件系统")
    state.template_strategy = TemplateStrategy(
        base_template_id="TEMPLATE_GENERAL_FUNCTIONAL",
        base_template_name="通用功能说明型软著文档",
        recommended_chapters=["引言", "软件概述", "核心功能说明"],
    )
    store.save_state(state)
    fake_orchestrator = FakeConfirmOrchestrator(store)
    app.dependency_overrides[get_workflow_orchestrator] = lambda: fake_orchestrator

    response = client.post(
        f"/api/runs/{state.run_id}/actions/confirm-doc-plan",
        json={"accepted": True, "note": "确认采用推荐方案"},
    )

    assert response.status_code == 200
    assert fake_orchestrator.calls == 1
    assert fake_orchestrator.decision is not None
    assert fake_orchestrator.decision.selected_base_template_id == "TEMPLATE_GENERAL_FUNCTIONAL"
    assert fake_orchestrator.decision.selected_top_level_chapters == [
        "引言",
        "软件概述",
        "核心功能说明",
    ]
    assert fake_orchestrator.decision.user_notes == "确认采用推荐方案"
    payload = response.json()
    assert payload["workspace"]["run_summary"]["stage_label"] == "文档方案已冻结，正在生成目录"
    loaded = store.load_state(state.run_id)
    assert loaded.workflow_status == WorkflowStatus.PLAN_FROZEN
    assert loaded.next_action == NextAction.CREATE_OUTLINE


def test_confirm_doc_plan_rejects_manual_modify_without_form(
    api_client: tuple[TestClient, StateStore],
) -> None:
    client, store = api_client
    state = store.create_initial_state()
    state.workflow_status = WorkflowStatus.USER_CONFIRM_REQUIRED
    state.next_action = NextAction.ASK_HUMAN_CONFIRMATION
    store.save_state(state)

    response = client.post(
        f"/api/runs/{state.run_id}/actions/confirm-doc-plan",
        json={"accepted": False},
    )

    assert response.status_code == 409
    assert response.json()["error_code"] == "cannot_auto_confirm"


def test_confirm_product_type_endpoint_not_reserved(
    api_client: tuple[TestClient, StateStore],
) -> None:
    client, store = api_client
    state = store.create_initial_state()
    state.workflow_status = WorkflowStatus.USER_CONFIRM_REQUIRED
    state.next_action = NextAction.ASK_HUMAN_CONFIRMATION
    state.diagnosis_result = DiagnosisResult(primary_type="Web/SaaS 平台")
    state.template_strategy = TemplateStrategy(
        base_template_id="TEMPLATE_WEB",
        base_template_name="Web 模板",
        recommended_chapters=["引言"],
    )
    store.save_state(state)
    fake_orchestrator = FakeConfirmOrchestrator(store)
    app.dependency_overrides[get_workflow_orchestrator] = lambda: fake_orchestrator

    response = client.post(
        f"/api/runs/{state.run_id}/actions/confirm-product-type",
        json={
            "selected_product_type": "工业软件",
            "use_agent_recommendation": False,
            "selected_doc_type": "technical_design",
            "reference_style_strength": "weak",
        },
    )

    assert response.status_code == 200
    assert fake_orchestrator.calls == 1
    assert store.load_state(state.run_id).diagnosis_result.primary_type == "工业软件"
    assert response.json()["workspace"]["settings"]["doc_output_type"] == "technical_design"


def test_strategy_settings_update_and_restart_endpoints(
    api_client: tuple[TestClient, StateStore],
) -> None:
    client, store = api_client
    state = store.create_initial_state()
    state.workflow_status = WorkflowStatus.USER_CONFIRM_REQUIRED
    state.next_action = NextAction.ASK_HUMAN_CONFIRMATION
    state.diagnosis_result = DiagnosisResult(primary_type="Web/SaaS 平台")
    state.template_strategy = TemplateStrategy(
        base_template_id="TEMPLATE_WEB",
        base_template_name="Web 模板",
        recommended_chapters=["引言"],
    )
    store.save_state(state)
    settings = {
        "product_type_hint": "industrial_software",
        "doc_output_type": "technical_design",
        "reference_style_strength": "weak",
    }

    response = client.post(f"/api/runs/{state.run_id}/settings", json=settings)

    assert response.status_code == 200
    updated = store.load_state(state.run_id)
    assert updated.template_strategy is None
    assert response.json()["workspace"]["settings"]["product_type_hint"] == "industrial_software"

    updated.workflow_status = WorkflowStatus.PLAN_FROZEN
    updated.next_action = NextAction.CREATE_OUTLINE
    updated.frozen_doc_plan = FrozenDocPlan(locked_status="locked")
    store.save_state(updated)

    blocked = client.post(f"/api/runs/{state.run_id}/settings", json=settings)
    restarted = client.post(f"/api/runs/{state.run_id}/restart-strategy", json=settings)

    assert blocked.status_code == 409
    assert blocked.json()["error_code"] == "strategy_reset_required"
    assert restarted.status_code == 200
    assert store.load_state(state.run_id).frozen_doc_plan is None


def test_workspace_view_includes_confirmation_card(
    api_client: tuple[TestClient, StateStore],
) -> None:
    client, store = api_client
    state = store.create_initial_state()
    state.workflow_status = WorkflowStatus.USER_CONFIRM_REQUIRED
    state.next_action = NextAction.ASK_HUMAN_CONFIRMATION
    state.diagnosis_result = DiagnosisResult(primary_type="通用软件系统")
    state.template_strategy = TemplateStrategy(
        base_template_id="TEMPLATE_GENERAL_FUNCTIONAL",
        base_template_name="通用功能说明型软著文档",
        recommended_chapters=["引言", "软件概述", "核心功能说明"],
    )
    store.save_state(state)

    response = client.get(f"/api/workspace/{state.run_id}")

    assert response.status_code == 200
    payload = response.json()
    cards = [
        message.get("card")
        for message in payload["messages"]
        if message.get("card") is not None
    ]
    assert cards
    card = cards[0]
    assert card["cardType"] == "doc_plan_confirm"
    assert card["title"] == "需要确认产品类型和文档策略"
    assert "产品类型：通用软件系统" in card["summary"]
    assert card["sections"] == ["引言", "软件概述", "核心功能说明"]
    assert card["actions"][0]["actionType"] == "use_agent_recommendation"
    assert card["actions"][0]["label"] == "采用系统推荐并继续"


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


def _api_source_item(
    source_type: SourceType,
    file_type: FileType,
    *,
    is_reference_source: bool = False,
    is_product_source: bool = True,
    allowed_usage: AllowedUsage = AllowedUsage.FACTUAL_EVIDENCE,
    corpus_type: CorpusType = CorpusType.PRODUCT_EVIDENCE,
) -> SourceItem:
    return SourceItem(
        source_type=source_type,
        file_type=file_type,
        corpus_type=corpus_type,
        allowed_usage=allowed_usage,
        file_name=f"{source_type.value}.{file_type.value}",
        file_path=f"sources/product/{source_type.value}.{file_type.value}",
        is_reference_source=is_reference_source,
        is_product_source=is_product_source,
        parse_status=ParseStatus.PENDING,
    )


def _save_verified_model_config(client: TestClient) -> None:
    response = client.post(
        "/api/model-config",
        json={
            "llm": {
                "provider": "qwen",
                "model": "qwen-plus",
                "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
                "api_key": "unit-llm-secret",
                "verified": True,
                "last_verified_at": "2026-06-10T00:00:00+00:00",
            },
            "embedding": {
                "provider": "jina",
                "model": "jina-embeddings-v3",
                "base_url": "https://api.jina.ai/v1",
                "api_key": "unit-embedding-secret",
                "verified": True,
                "last_verified_at": "2026-06-10T00:00:00+00:00",
            },
        },
    )
    assert response.status_code == 200


@pytest.mark.parametrize(
    ("path", "payload"),
    [
        ("/api/runs/bad-run-id/actions/next", {}),
        ("/api/runs/bad-run-id/actions/start", {}),
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
