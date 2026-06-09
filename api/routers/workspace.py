from __future__ import annotations

from fastapi import APIRouter, Depends

from api.deps import get_workspace_view_service
from api.run_id_guard import validate_run_id
from api.schemas import WorkspaceView
from api.services.workspace_view_service import WorkspaceViewService

router = APIRouter(tags=["workspace"])


@router.get("/workspace/{run_id}", response_model=WorkspaceView)
def get_workspace(
    run_id: str,
    service: WorkspaceViewService = Depends(get_workspace_view_service),
) -> WorkspaceView:
    validate_run_id(run_id)
    return service.get_workspace(run_id)
