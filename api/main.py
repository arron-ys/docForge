from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .errors import ApiError
from .routers import artifacts, diagnostics, runs, sources, workspace
from .schemas import ApiErrorResponse

app = FastAPI(title="DocForge API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(ApiError)
async def handle_api_error(_request: Request, exc: ApiError) -> JSONResponse:
    payload = ApiErrorResponse(
        error_code=exc.error_code,
        message=exc.message,
        recoverable=exc.recoverable,
        suggested_action=exc.suggested_action,
    )
    return JSONResponse(status_code=exc.status_code, content=payload.model_dump())


app.include_router(workspace.router, prefix="/api")
app.include_router(sources.router, prefix="/api")
app.include_router(runs.router, prefix="/api")
app.include_router(diagnostics.router, prefix="/api")
app.include_router(artifacts.router, prefix="/api")


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}

