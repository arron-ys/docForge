from __future__ import annotations

from fastapi import APIRouter, Depends, File, UploadFile
from starlette.status import HTTP_501_NOT_IMPLEMENTED

from api.deps import get_source_upload_service
from api.errors import ApiError
from api.run_id_guard import validate_run_id
from api.schemas import FileUploadResult, UploadNoteRequest
from api.services.source_upload_service import SourceUploadService

router = APIRouter(tags=["sources"])


@router.post("/runs/{run_id}/sources/reference", response_model=FileUploadResult)
def upload_reference_source(
    run_id: str,
    file: UploadFile = File(...),
    service: SourceUploadService = Depends(get_source_upload_service),
) -> FileUploadResult:
    validate_run_id(run_id)
    return FileUploadResult(source=service.upload_reference(run_id, file))


@router.post("/runs/{run_id}/sources/product", response_model=FileUploadResult)
def upload_product_source(
    run_id: str,
    file: UploadFile = File(...),
    service: SourceUploadService = Depends(get_source_upload_service),
) -> FileUploadResult:
    validate_run_id(run_id)
    return FileUploadResult(source=service.upload_product(run_id, file))


@router.post("/runs/{run_id}/sources/screenshots", response_model=FileUploadResult)
def upload_screenshot_source(
    run_id: str,
    file: UploadFile = File(...),
    service: SourceUploadService = Depends(get_source_upload_service),
) -> FileUploadResult:
    validate_run_id(run_id)
    return FileUploadResult(source=service.upload_screenshot(run_id, file))


@router.post("/runs/{run_id}/sources/notes")
def upload_note_source(run_id: str, _payload: UploadNoteRequest) -> None:
    validate_run_id(run_id)
    raise ApiError(
        error_code="notes_upload_not_implemented",
        message="文本备注接口已预留，当前 Sprint 暂未接入。",
        status_code=HTTP_501_NOT_IMPLEMENTED,
        suggested_action="请先上传参考资料、自有产品资料或产品截图。",
    )
