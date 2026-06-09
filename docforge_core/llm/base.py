"""LLM provider abstractions."""

import json
import re
from abc import ABC, abstractmethod
from json import JSONDecodeError
from typing import Any, Literal

from pydantic import BaseModel, Field


class LLMMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class LLMResponse(BaseModel):
    content: str
    model: str
    provider: str
    raw: dict[str, Any] = Field(default_factory=dict)


class ProviderError(RuntimeError):
    """Raised when a provider request fails."""


class LLMProvider(ABC):
    """Common interface used by future agents."""

    @abstractmethod
    def generate_text(
        self,
        messages: list[LLMMessage],
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        """Generate text from chat messages."""

    def generate_json(
        self,
        messages: list[LLMMessage],
        temperature: float = 0.1,
        max_tokens: int | None = None,
    ) -> dict[str, Any]:
        """Generate JSON and parse it into a dictionary."""
        response = self.generate_text(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return self._extract_json_object(response.content)

    @staticmethod
    def _extract_json_object(text: str) -> dict[str, Any]:
        """Extract a JSON object from plain, fenced, or explanatory model output."""
        candidates = [text]
        candidates.extend(
            match.group(1)
            for match in re.finditer(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.IGNORECASE | re.DOTALL)
        )

        first_brace = text.find("{")
        last_brace = text.rfind("}")
        if first_brace >= 0 and last_brace > first_brace:
            candidates.append(text[first_brace : last_brace + 1])

        parsed_non_object = False
        for candidate in candidates:
            try:
                value = json.loads(candidate.strip())
            except JSONDecodeError:
                continue
            if isinstance(value, dict):
                return value
            parsed_non_object = True

        if parsed_non_object:
            raise ValueError("模型 JSON 输出必须是对象")
        raise ValueError("模型输出不包含合法 JSON 对象")
