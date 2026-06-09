from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse

from api.deps import get_artifact_service
from api.services.artifact_service import ArtifactService

router = APIRouter(tags=["artifacts"])


@router.get("/artifacts/{artifact_id}/download")
def download_artifact(
    artifact_id: str,
    service: ArtifactService = Depends(get_artifact_service),
) -> FileResponse:
    path = service.resolve_download(artifact_id)
    return FileResponse(
        path=path,
        filename=path.name,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )

