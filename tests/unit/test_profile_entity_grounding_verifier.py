from typing import Any

from docforge_core.agents.profile_entity_grounding_verifier import (
    ProductProfileEntityGroundingVerifier,
)
from docforge_core.llm.base import LLMMessage
from docforge_core.llm.mock_provider import MockLLMProvider


def _entity(index: int = 0) -> dict[str, Any]:
    return {
        "entity_index": index,
        "entity_type": "business_object",
        "name": "三维模型",
        "description": None,
        "steps": None,
        "implementation_status": "current",
        "supporting_evidence_ids": ["ev_product"],
        "supporting_quotes": ["当前版本支持三维模型导入与查看"],
    }


def _result(supported: bool, index: int = 0) -> dict[str, Any]:
    return {
        "entity_index": index,
        "supported": supported,
        "name_supported": supported,
        "entity_type_supported": supported,
        "implementation_status_supported": supported,
        "corrected_implementation_status": None,
        "reason": "semantic result",
    }


def test_empty_entities_return_empty_without_llm_call() -> None:
    provider = MockLLMProvider(json_response={"results": []})

    result = ProductProfileEntityGroundingVerifier(provider).verify_entities([], {})

    assert result == []
    assert provider.json_call_count == 0


def test_profile_entity_verifier_parses_supported_true() -> None:
    provider = MockLLMProvider(json_response={"results": [_result(True)]})

    result = ProductProfileEntityGroundingVerifier(provider).verify_entities(
        [_entity()],
        {"ev_product": "当前版本支持三维模型导入与查看"},
    )

    assert result[0]["supported"] is True
    assert result[0]["implementation_status_supported"] is True


def test_profile_entity_verifier_parses_supported_false() -> None:
    provider = MockLLMProvider(json_response={"results": [_result(False)]})

    result = ProductProfileEntityGroundingVerifier(provider).verify_entities(
        [_entity()],
        {"ev_product": "当前版本支持三维模型导入与查看"},
    )

    assert result[0]["supported"] is False


def test_profile_entity_verifier_missing_results_fails_closed() -> None:
    provider = MockLLMProvider(json_response={})

    result = ProductProfileEntityGroundingVerifier(provider).verify_entities(
        [_entity()],
        {"ev_product": "当前版本支持三维模型导入与查看"},
    )

    assert result[0]["supported"] is False
    assert result[0]["implementation_status_supported"] is False
    assert "fail closed" in result[0]["reason"]


def test_profile_entity_verifier_missing_entity_result_fails_closed() -> None:
    provider = MockLLMProvider(json_response={"results": []})

    result = ProductProfileEntityGroundingVerifier(provider).verify_entities(
        [_entity()],
        {"ev_product": "当前版本支持三维模型导入与查看"},
    )

    assert result[0]["supported"] is False
    assert result[0]["implementation_status_supported"] is False
    assert "未返回" in result[0]["reason"]


def test_profile_entity_verifier_json_failure_fails_closed() -> None:
    class FailingProvider(MockLLMProvider):
        def generate_json(
            self,
            messages: list[LLMMessage],
            temperature: float = 0.1,
            max_tokens: int | None = None,
        ) -> dict[str, Any]:
            raise ValueError("bad entity verifier json")

    result = ProductProfileEntityGroundingVerifier(FailingProvider()).verify_entities(
        [_entity(), _entity(1)],
        {"ev_product": "当前版本支持三维模型导入与查看"},
    )

    assert all(item["supported"] is False for item in result)
    assert all(item["implementation_status_supported"] is False for item in result)
    assert all("解析失败" in item["reason"] for item in result)


def test_profile_entity_verifier_does_not_call_external_api() -> None:
    provider = MockLLMProvider(json_response={"results": [_result(True)]})

    ProductProfileEntityGroundingVerifier(provider).verify_entities(
        [_entity()],
        {"ev_product": "当前版本支持三维模型导入与查看"},
    )

    assert provider.json_call_count == 1


def test_profile_entity_verifier_preserves_corrected_planned_status() -> None:
    correction = _result(True)
    correction.update(
        {
            "implementation_status_supported": False,
            "corrected_implementation_status": "planned",
        }
    )
    provider = MockLLMProvider(json_response={"results": [correction]})

    result = ProductProfileEntityGroundingVerifier(provider).verify_entities(
        [_entity()],
        {"ev_product": "未来规划中将支持三维模型页面"},
    )

    assert result[0]["implementation_status_supported"] is False
    assert result[0]["corrected_implementation_status"] == "planned"


def test_missing_implementation_status_supported_defaults_false() -> None:
    raw_result = _result(True)
    raw_result.pop("implementation_status_supported")
    provider = MockLLMProvider(json_response={"results": [raw_result]})

    result = ProductProfileEntityGroundingVerifier(provider).verify_entities(
        [_entity()],
        {"ev_product": "当前版本支持三维模型导入与查看"},
    )

    assert result[0]["implementation_status_supported"] is False
