
import pytest

from docforge_core.config.settings import Settings
from docforge_core.llm.base import LLMMessage, LLMProvider, LLMResponse
from docforge_core.llm.deepseek_provider import DeepSeekProvider
from docforge_core.llm.mock_provider import MockLLMProvider
from docforge_core.llm.provider_factory import create_llm_provider
from docforge_core.llm.qwen_provider import QwenProvider


class TextResponseProvider(LLMProvider):
    def __init__(self, content: str) -> None:
        self.content = content

    def generate_text(
        self,
        messages: list[LLMMessage],
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        return LLMResponse(content=self.content, model="test", provider="test")


def test_mock_llm_provider_generate_text_returns_fixed_text() -> None:
    provider = MockLLMProvider(text_response="fixed")

    response = provider.generate_text([LLMMessage(role="user", content="hello")])

    assert response.content == "fixed"
    assert response.provider == "mock"


def test_mock_llm_provider_generate_json_returns_fixed_dict() -> None:
    provider = MockLLMProvider(json_response={"answer": 1})

    assert provider.generate_json([LLMMessage(role="user", content="json")]) == {"answer": 1}


def test_mock_llm_provider_returns_sequential_json_responses() -> None:
    provider = MockLLMProvider(json_responses=[{"answer": 1}, {"answer": 2}])
    messages = [LLMMessage(role="user", content="json")]

    assert provider.generate_json(messages) == {"answer": 1}
    assert provider.generate_json(messages) == {"answer": 2}
    assert provider.json_call_count == 2
    with pytest.raises(RuntimeError, match="已耗尽"):
        provider.generate_json(messages)


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        ('{"answer": 1}', {"answer": 1}),
        ('```json\n{"answer": 2}\n```', {"answer": 2}),
        ('说明文字\n{"answer": 3}\n结束文字', {"answer": 3}),
    ],
)
def test_generate_json_extracts_object(content: str, expected: dict[str, int]) -> None:
    provider = TextResponseProvider(content)

    assert provider.generate_json([LLMMessage(role="user", content="json")]) == expected


def test_generate_json_array_raises_value_error() -> None:
    provider = TextResponseProvider("[1, 2, 3]")

    with pytest.raises(ValueError, match="对象"):
        provider.generate_json([LLMMessage(role="user", content="json")])


def test_generate_json_invalid_json_raises_value_error() -> None:
    class BadJsonProvider(LLMProvider):
        def generate_text(
            self,
            messages: list[LLMMessage],
            temperature: float = 0.2,
            max_tokens: int | None = None,
        ) -> LLMResponse:
            return LLMResponse(content="not-json", model="bad", provider="bad")

    with pytest.raises(ValueError, match="JSON"):
        BadJsonProvider().generate_json([LLMMessage(role="user", content="json")])


def test_provider_factory_can_create_mock_provider() -> None:
    provider = create_llm_provider(Settings(default_llm_provider="mock"))

    assert isinstance(provider, MockLLMProvider)


def test_provider_factory_unknown_provider_raises_value_error() -> None:
    with pytest.raises(ValueError):
        create_llm_provider(Settings(default_llm_provider="unknown"))


def test_qwen_provider_missing_api_key_raises_clear_error() -> None:
    with pytest.raises(ValueError, match="QWEN_API_KEY"):
        QwenProvider(Settings(qwen_api_key="", qwen_base_url="https://example.com"))


def test_deepseek_provider_missing_api_key_raises_clear_error() -> None:
    with pytest.raises(ValueError, match="DEEPSEEK_API_KEY"):
        DeepSeekProvider(Settings(deepseek_api_key="", deepseek_base_url="https://example.com"))


def test_llm_provider_tests_do_not_require_network() -> None:
    provider = MockLLMProvider(text_response="offline")
    response = provider.generate_text([LLMMessage(role="user", content="hello")])
    assert response.content == "offline"
