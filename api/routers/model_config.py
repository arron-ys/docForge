from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends

from docforge_core.config.runtime_model_config import (
    RuntimeModelConfig,
    RuntimeModelConfigService,
    RuntimeProviderConfig,
    RuntimeProviderConfigUpdate,
)

from ..deps import get_runtime_model_config_service_dep
from ..schemas import (
    ModelConfigView,
    ModelProviderConfigPayload,
    ModelProviderConfigView,
    SaveModelConfigRequest,
    TestModelConnectionRequest,
    TestModelConnectionResponse,
)

router = APIRouter(tags=["model-config"])


@router.get("/model-config", response_model=ModelConfigView)
def get_model_config(
    service: RuntimeModelConfigService = Depends(get_runtime_model_config_service_dep),
) -> ModelConfigView:
    return _model_config_view(service.load_config(), service)


@router.post("/model-config", response_model=ModelConfigView)
def save_model_config(
    request: SaveModelConfigRequest,
    service: RuntimeModelConfigService = Depends(get_runtime_model_config_service_dep),
) -> ModelConfigView:
    config = service.update_config(
        llm=_payload_to_update(request.llm),
        embedding=_payload_to_update(request.embedding),
    )
    return _model_config_view(config, service)


@router.post("/model-config/test-llm", response_model=TestModelConnectionResponse)
def test_llm_connection(
    request: TestModelConnectionRequest,
    service: RuntimeModelConfigService = Depends(get_runtime_model_config_service_dep),
) -> TestModelConnectionResponse:
    result = service.test_llm_connection(
        provider=request.provider,
        model=request.model,
        base_url=request.base_url,
        api_key=request.api_key,
    )
    return _test_response(result.verified, result.message, result.error_code)


@router.post("/model-config/test-embedding", response_model=TestModelConnectionResponse)
def test_embedding_connection(
    request: TestModelConnectionRequest,
    service: RuntimeModelConfigService = Depends(get_runtime_model_config_service_dep),
) -> TestModelConnectionResponse:
    result = service.test_embedding_connection(
        provider=request.provider,
        model=request.model,
        base_url=request.base_url,
        api_key=request.api_key,
    )
    return _test_response(result.verified, result.message, result.error_code)


def _payload_to_update(
    payload: ModelProviderConfigPayload | None,
) -> RuntimeProviderConfigUpdate | None:
    if payload is None:
        return None
    return RuntimeProviderConfigUpdate(
        provider=payload.provider,
        model=payload.model,
        base_url=payload.base_url,
        api_key=payload.api_key,
        clear_api_key=payload.clear_api_key,
        verified=payload.verified,
        last_verified_at=payload.last_verified_at,
    )


def _model_config_view(
    config: RuntimeModelConfig,
    service: RuntimeModelConfigService,
) -> ModelConfigView:
    return ModelConfigView(
        llm=_provider_config_view(config.llm, service),
        embedding=_provider_config_view(config.embedding, service),
    )


def _provider_config_view(
    config: RuntimeProviderConfig | None,
    service: RuntimeModelConfigService,
) -> ModelProviderConfigView | None:
    if config is None:
        return None
    masked_key = service.mask_api_key(config.api_key)
    return ModelProviderConfigView(
        provider=config.provider,
        model=config.model,
        base_url=config.base_url,
        has_api_key=bool(config.api_key),
        masked_api_key=masked_key,
        verified=config.verified,
        last_verified_at=config.last_verified_at,
    )


def _test_response(
    verified: bool,
    message: str,
    error_code: str | None,
) -> TestModelConnectionResponse:
    return TestModelConnectionResponse(
        verified=verified,
        message=message,
        error_code=error_code,
        last_verified_at=datetime.now(UTC).isoformat() if verified else None,
    )
