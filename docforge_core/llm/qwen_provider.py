"""Qwen OpenAI-compatible provider."""

from typing import Any

import httpx

from docforge_core.config.runtime_model_config import (
    RuntimeProviderConfig,
    get_runtime_model_config_service,
)
from docforge_core.config.settings import Settings, get_settings

from .base import LLMMessage, LLMProvider, LLMResponse, ProviderError


class QwenProvider(LLMProvider):
    provider_name = "qwen"

    def __init__(
        self,
        settings: Settings | None = None,
        runtime_config: RuntimeProviderConfig | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        if runtime_config is None and settings is None:
            candidate = get_runtime_model_config_service().get_llm_config()
            if candidate and candidate.provider == "qwen":
                runtime_config = candidate

        self.api_key = runtime_config.api_key if runtime_config else self.settings.qwen_api_key
        self.base_url = runtime_config.base_url if runtime_config else self.settings.qwen_base_url
        self.model = runtime_config.model if runtime_config else self.settings.qwen_model
        if not self.api_key:
            raise ValueError("模型密钥未配置，请在右上角“配置密钥”中填写并测试连接")
        if not self.base_url:
            raise ValueError("模型 BaseURL 未配置，请在右上角“配置密钥”中填写并测试连接")

    def generate_text(
        self,
        messages: list[LLMMessage],
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [message.model_dump() for message in messages],
            "temperature": temperature,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens

        try:
            response = httpx.post(
                self._chat_completions_url(),
                headers={"Authorization": f"Bearer {self.api_key}"},
                json=payload,
                timeout=60,
            )
            response.raise_for_status()
            raw = response.json()
            content = raw["choices"][0]["message"]["content"]
        except Exception as exc:
            raise ProviderError(f"QwenProvider 请求失败: {exc}") from exc

        return LLMResponse(
            content=str(content),
            model=self.model,
            provider=self.provider_name,
            raw=raw,
        )

    def _chat_completions_url(self) -> str:
        base_url = self.base_url.rstrip("/")
        if base_url.endswith("/chat/completions"):
            return base_url
        return f"{base_url}/chat/completions"
