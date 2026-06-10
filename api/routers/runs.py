from __future__ import annotations

from fastapi import APIRouter, Depends

from api.deps import get_run_action_service, get_workspace_view_service
from api.run_id_guard import validate_run_id
from api.schemas import (
    ActionResultView,
    ConfirmDocPlanRequest,
    ConfirmProductTypeRequest,
    CreateRunRequest,
    CreateRunResponse,
    RunListView,
)
from api.services.run_action_service import RunActionService
from api.services.workspace_view_service import WorkspaceViewService

router = APIRouter(tags=["runs"])


@router.get("/runs", response_model=RunListView)
def list_runs(
    service: WorkspaceViewService = Depends(get_workspace_view_service),
) -> RunListView:
    return service.list_runs()


@router.post("/runs", response_model=CreateRunResponse)
def create_run(
    payload: CreateRunRequest | None = None,
    service: WorkspaceViewService = Depends(get_workspace_view_service),
) -> CreateRunResponse:
    return service.create_run(payload.project_name if payload else None)


@router.post("/runs/{run_id}/actions/next", response_model=ActionResultView)
def run_next_action(
    run_id: str,
    service: RunActionService = Depends(get_run_action_service),
) -> ActionResultView:
    validate_run_id(run_id)
    return service.run_next(run_id)


@router.post("/runs/{run_id}/actions/confirm-product-type", response_model=ActionResultView)
def confirm_product_type(
    run_id: str,
    _payload: ConfirmProductTypeRequest,
    service: RunActionService = Depends(get_run_action_service),
) -> ActionResultView:
    validate_run_id(run_id)
    return service.confirm_product_type(run_id)


@router.post("/runs/{run_id}/actions/confirm-doc-plan", response_model=ActionResultView)
def confirm_doc_plan(
    run_id: str,
    _payload: ConfirmDocPlanRequest,
    service: RunActionService = Depends(get_run_action_service),
) -> ActionResultView:
    validate_run_id(run_id)
    return service.confirm_doc_plan(run_id)


@router.post("/runs/{run_id}/actions/export-final-docx", response_model=ActionResultView)
def export_final_docx(
    run_id: str,
    service: RunActionService = Depends(get_run_action_service),
) -> ActionResultView:
    validate_run_id(run_id)
    return service.export_final_docx(run_id)


@router.post("/runs/{run_id}/actions/export-risk-docx", response_model=ActionResultView)
def export_risk_docx(
    run_id: str,
    service: RunActionService = Depends(get_run_action_service),
) -> ActionResultView:
    validate_run_id(run_id)
    return service.export_risk_docx(run_id)
