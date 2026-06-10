from __future__ import annotations

import json
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import httpx


DEFAULT_QWEN_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
DEFAULT_QWEN_MODEL = "qwen-plus"
DEFAULT_JINA_BASE_URL = "https://api.jina.ai/v1"
DEFAULT_JINA_MODEL = "jina-embeddings-v3"


@dataclass(slots=True)
class RuntimeProviderConfig:
    provider: str = ""
    model: str = ""
    base_url: str = ""
    api_key: str = ""
    verified: bool = False
    last_verified_at: str | None = None

    @property
    def is_complete(self) -> bool:
        return bool(
            self.provider.strip()
            and self.model.strip()
            and self.base_url.strip()
            and self.api_key.strip()
        )


@dataclass(slots=True)
class RuntimeModelConfig:
    llm: RuntimeProviderConfig | None = None
    embedding: RuntimeProviderConfig | None = None


@dataclass(slots=True)
class RuntimeProviderConfigUpdate:
    provider: str
    model: str
    base_url: str
    api_key: str | None = None
    clear_api_key: bool = False
    verified: bool | None = None
    last_verified_at: str | None = None


@dataclass(slots=True)
class ConnectionTestResult:
    verified: bool
    message: str
    error_code: str | None = None


def default_model_config_path() -> Path:
    override = os.environ.get("DOCFORGE_MODEL_CONFIG_PATH", "").strip()
    if override:
        return Path(override).expanduser()

    if os.name == "nt":
        app_data = os.environ.get("APPDATA", "").strip()
        base_dir = Path(app_data) / "DocForge" if app_data else Path.home() / "AppData" / "Roaming" / "DocForge"
        return base_dir / "model_config.json"

    return Path.home() / ".docforge" / "model_config.json"


class RuntimeModelConfigService:
    def __init__(self, config_path: Path | None = None) -> None:
        self.config_path = config_path or default_model_config_path()

    def load_config(self) -> RuntimeModelConfig:
        if not self.config_path.exists():
            return RuntimeModelConfig()

        try:
            raw = json.loads(self.config_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return RuntimeModelConfig()

        if not isinstance(raw, dict):
            return RuntimeModelConfig()

        return RuntimeModelConfig(
            llm=self._parse_provider_config(raw.get("llm")),
            embedding=self._parse_provider_config(raw.get("embedding")),
        )

    def save_config(self, config: RuntimeModelConfig) -> RuntimeModelConfig:
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        payload = self._config_to_dict(config)
        temp_path = self.config_path.with_suffix(f"{self.config_path.suffix}.tmp")
        temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temp_path, self.config_path)
        try:
            self.config_path.chmod(0o600)
        except OSError:
            pass
        return config

    def update_config(
        self,
        llm: RuntimeProviderConfigUpdate | None = None,
        embedding: RuntimeProviderConfigUpdate | None = None,
    ) -> RuntimeModelConfig:
        current = self.load_config()
        updated = RuntimeModelConfig(
            llm=self._merge_provider_config(current.llm, llm),
            embedding=self._merge_provider_config(current.embedding, embedding),
        )
        return self.save_config(updated)

    def get_llm_config(self) -> RuntimeProviderConfig | None:
        config = self.load_config().llm
        return config if config and config.is_complete else None

    def get_embedding_config(self) -> RuntimeProviderConfig | None:
        config = self.load_config().embedding
        return config if config and config.is_complete else None

    def clear_config(self) -> None:
        try:
            self.config_path.unlink()
        except FileNotFoundError:
            return

    def mask_api_key(self, api_key: str | None) -> str | None:
        value = (api_key or "").strip()
        if not value:
            return None
        if len(value) <= 8:
            return f"{value[:2]}****{value[-2:]}"
        return f"{value[:4]}****{value[-4:]}"

    def test_llm_connection(
        self,
        provider: str,
        model: str,
        base_url: str,
        api_key: str | None = None,
    ) -> ConnectionTestResult:
        normalized_provider = provider.strip().lower()
        if normalized_provider != "qwen":
            return ConnectionTestResult(
                verified=False,
                message="当前版本仅支持测试 Qwen LLM 连接。",
                error_code="unsupported_provider",
            )

        resolved_key = self._resolve_saved_api_key("llm", normalized_provider, api_key)
        if not resolved_key:
            return ConnectionTestResult(
                verified=False,
                message="请先输入 LLM API Key。",
                error_code="missing_api_key",
            )

        resolved_model = model.strip() or DEFAULT_QWEN_MODEL
        resolved_base_url = base_url.strip() or DEFAULT_QWEN_BASE_URL
        url = self._endpoint_url(resolved_base_url, "chat/completions")
        try:
            response = httpx.post(
                url,
                headers={"Authorization": f"Bearer {resolved_key}"},
                json={
                    "model": resolved_model,
                    "messages": [{"role": "user", "content": "ping"}],
                    "max_tokens": 8,
                    "temperature": 0,
                },
                timeout=30,
            )
            response.raise_for_status()
        except Exception as exc:
            return self._map_connection_error(exc)

        return ConnectionTestResult(verified=True, message="LLM 连接测试通过。")

    def test_embedding_connection(
        self,
        provider: str,
        model: str,
        base_url: str,
        api_key: str | None = None,
    ) -> ConnectionTestResult:
        normalized_provider = provider.strip().lower()
        if normalized_provider != "jina":
            return ConnectionTestResult(
                verified=False,
                message="当前版本仅支持测试 Jina Embedding 连接。",
                error_code="unsupported_provider",
            )

        resolved_key = self._resolve_saved_api_key("embedding", normalized_provider, api_key)
        if not resolved_key:
            return ConnectionTestResult(
                verified=False,
                message="请先输入 Embedding API Key。",
                error_code="missing_api_key",
            )

        resolved_model = model.strip() or DEFAULT_JINA_MODEL
        resolved_base_url = base_url.strip() or DEFAULT_JINA_BASE_URL
        url = self._endpoint_url(resolved_base_url, "embeddings")
        try:
            response = httpx.post(
                url,
                headers={"Authorization": f"Bearer {resolved_key}"},
                json={"model": resolved_model, "input": ["ping"]},
                timeout=30,
            )
            response.raise_for_status()
        except Exception as exc:
            return self._map_connection_error(exc)

        return ConnectionTestResult(verified=True, message="Embedding 连接测试通过。")

    def _parse_provider_config(self, raw: object) -> RuntimeProviderConfig | None:
        if not isinstance(raw, dict):
            return None
        return RuntimeProviderConfig(
            provider=self._string_value(raw.get("provider")),
            model=self._string_value(raw.get("model")),
            base_url=self._string_value(raw.get("base_url")),
            api_key=self._string_value(raw.get("api_key")),
            verified=bool(raw.get("verified", False)),
            last_verified_at=self._optional_string_value(raw.get("last_verified_at")),
        )

    def _merge_provider_config(
        self,
        current: RuntimeProviderConfig | None,
        update: RuntimeProviderConfigUpdate | None,
    ) -> RuntimeProviderConfig | None:
        if update is None:
            return current

        previous_key = current.api_key if current else ""
        next_key = self._string_value(update.api_key)
        if update.clear_api_key:
            api_key = ""
        elif next_key:
            api_key = next_key
        else:
            api_key = previous_key

        provider = update.provider.strip().lower()
        model = update.model.strip()
        base_url = update.base_url.strip().rstrip("/")
        changed = (
            current is None
            or current.provider != provider
            or current.model != model
            or current.base_url.rstrip("/") != base_url
            or current.api_key != api_key
        )

        if update.verified is None:
            verified = bool(current and current.verified and not changed)
            last_verified_at = current.last_verified_at if verified and current else None
        else:
            verified = bool(update.verified)
            last_verified_at = update.last_verified_at if verified else None

        return RuntimeProviderConfig(
            provider=provider,
            model=model,
            base_url=base_url,
            api_key=api_key,
            verified=verified,
            last_verified_at=last_verified_at,
        )

    def _resolve_saved_api_key(
        self,
        section: str,
        provider: str,
        api_key: str | None,
    ) -> str:
        candidate = (api_key or "").strip()
        if candidate:
            return candidate

        saved_config = self.load_config()
        saved_section = saved_config.llm if section == "llm" else saved_config.embedding
        if saved_section and saved_section.provider.strip().lower() == provider:
            return saved_section.api_key.strip()
        return ""

    def _map_connection_error(self, exc: Exception) -> ConnectionTestResult:
        if isinstance(exc, httpx.TimeoutException):
            return ConnectionTestResult(
                verified=False,
                message="连接超时，请检查网络、代理或服务地址。",
                error_code="timeout",
            )

        if isinstance(exc, httpx.HTTPStatusError):
            status_code = exc.response.status_code
            body = self._safe_response_body(exc.response)
            if self._contains_quota_error(body):
                return ConnectionTestResult(
                    verified=False,
                    message="当前账号额度不足，请检查模型服务账号余额或额度。",
                    error_code="insufficient_quota",
                )
            if status_code in {401, 403}:
                return ConnectionTestResult(
                    verified=False,
                    message="API Key 无效或没有权限，请检查后重试。",
                    error_code="invalid_api_key",
                )
            if status_code == 404:
                return ConnectionTestResult(
                    verified=False,
                    message="BaseURL 或模型名称可能不正确，请检查服务地址和模型名称。",
                    error_code="not_found",
                )
            if status_code == 429:
                return ConnectionTestResult(
                    verified=False,
                    message="当前账号请求过于频繁或额度受限，请稍后重试。",
                    error_code="rate_limited",
                )
            if 500 <= status_code < 600:
                return ConnectionTestResult(
                    verified=False,
                    message="模型服务暂时不可用，请稍后重试。",
                    error_code="provider_unavailable",
                )

        if isinstance(exc, httpx.RequestError):
            return ConnectionTestResult(
                verified=False,
                message="无法连接模型服务，请检查 BaseURL 和网络环境。",
                error_code="connection_error",
            )

        return ConnectionTestResult(
            verified=False,
            message="连接测试失败，请检查 API Key、BaseURL、模型名称和网络环境。",
            error_code="unknown",
        )

    def _safe_response_body(self, response: httpx.Response) -> str:
        try:
            return response.text[:1000].lower()
        except Exception:
            return ""

    def _contains_quota_error(self, body: str) -> bool:
        return any(
            marker in body
            for marker in (
                "insufficient_quota",
                "insufficient balance",
                "quota",
                "余额不足",
                "额度不足",
            )
        )

    def _endpoint_url(self, base_url: str, suffix: str) -> str:
        normalized = base_url.strip().rstrip("/")
        if normalized.endswith(f"/{suffix}"):
            return normalized
        return f"{normalized}/{suffix}"

    def _config_to_dict(self, config: RuntimeModelConfig) -> dict[str, Any]:
        return {
            "llm": self._provider_config_to_dict(config.llm),
            "embedding": self._provider_config_to_dict(config.embedding),
        }

    def _provider_config_to_dict(self, config: RuntimeProviderConfig | None) -> dict[str, Any] | None:
        if config is None:
            return None
        return {
            "provider": config.provider,
            "model": config.model,
            "base_url": config.base_url,
            "api_key": config.api_key,
            "verified": config.verified,
            "last_verified_at": config.last_verified_at,
        }

    def _string_value(self, value: object) -> str:
        return str(value).strip() if value is not None else ""

    def _optional_string_value(self, value: object) -> str | None:
        candidate = self._string_value(value)
        return candidate or None


@lru_cache(maxsize=1)
def get_runtime_model_config_service() -> RuntimeModelConfigService:
    return RuntimeModelConfigService()
