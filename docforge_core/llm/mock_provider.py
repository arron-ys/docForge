"""Mock LLM provider for tests."""

from copy import deepcopy
from typing import Any

from .base import LLMMessage, LLMProvider, LLMResponse


class MockLLMProvider(LLMProvider):
    provider_name = "mock"

    def __init__(
        self,
        text_response: str = "mock response",
        json_response: dict[str, Any] | None = None,
        json_responses: list[dict[str, Any]] | None = None,
    ) -> None:
        self.text_response = text_response
        self.json_response = json_response if json_response is not None else {"ok": True}
        self.json_responses = list(json_responses) if json_responses is not None else None
        self.json_call_count = 0

    def generate_text(
        self,
        messages: list[LLMMessage],
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        return LLMResponse(
            content=self.text_response,
            model="mock",
            provider=self.provider_name,
            raw={"messages": [message.model_dump() for message in messages]},
        )

    def generate_json(
        self,
        messages: list[LLMMessage],
        temperature: float = 0.1,
        max_tokens: int | None = None,
    ) -> dict[str, Any]:
        self.json_call_count += 1
        if self.json_responses is not None:
            index = self.json_call_count - 1
            if index >= len(self.json_responses):
                raise RuntimeError("MockLLMProvider json_responses 已耗尽")
            return deepcopy(self.json_responses[index])
        return deepcopy(self.json_response)
