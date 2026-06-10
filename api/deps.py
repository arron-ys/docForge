from __future__ import annotations

from functools import lru_cache

from fastapi import Depends

from docforge_core.config.runtime_model_config import (
    RuntimeModelConfigService,
    get_runtime_model_config_service,
)
from docforge_core.io.state_store import StateStore
from docforge_core.workflow import WorkflowDiagnosticsService, WorkflowOrchestratorService

from .services.artifact_service import ArtifactService
from .services.run_action_service import RunActionService
from .services.source_upload_service import SourceUploadService
from .services.workspace_view_service import WorkspaceViewService


@lru_cache(maxsize=1)
def get_state_store() -> StateStore:
    return StateStore()


def get_runtime_model_config_service_dep() -> RuntimeModelConfigService:
    return get_runtime_model_config_service()


def get_workspace_view_service(
    state_store: StateStore = Depends(get_state_store),
) -> WorkspaceViewService:
    return WorkspaceViewService(state_store)


def get_source_upload_service(
    state_store: StateStore = Depends(get_state_store),
) -> SourceUploadService:
    return SourceUploadService(state_store)


def get_run_action_service(
    state_store: StateStore = Depends(get_state_store),
    workspace_service: WorkspaceViewService = Depends(get_workspace_view_service),
) -> RunActionService:
    return RunActionService(
        state_store=state_store,
        orchestrator=WorkflowOrchestratorService(state_store),
        workspace_service=workspace_service,
    )


def get_diagnostics_service(
    state_store: StateStore = Depends(get_state_store),
) -> WorkflowDiagnosticsService:
    return WorkflowDiagnosticsService(state_store)


def get_artifact_service(
    state_store: StateStore = Depends(get_state_store),
) -> ArtifactService:
    return ArtifactService(state_store)
