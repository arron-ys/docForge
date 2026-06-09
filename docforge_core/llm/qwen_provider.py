"""Qwen OpenAI-compatible provider."""

from typing import Any

import httpx

from docforge_core.config.settings import Settings, get_settings

from .base import LLMMessage, LLMProvider, LLMResponse, ProviderError


class QwenProvider(LLMProvider):
    provider_name = "qwen"

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.api_key = self.settings.qwen_api_key
        self.base_url = self.settings.qwen_base_url
        self.model = self.settings.qwen_model
        if not self.api_key:
            raise ValueError("QWEN_API_KEY 未配置")
        if not self.base_url:
            raise ValueError("QWEN_BASE_URL 未配置")

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
