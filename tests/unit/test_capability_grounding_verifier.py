from typing import Any

from docforge_core.agents.capability_grounding_verifier import (
    ProductCapabilityGroundingVerifier,
)
from docforge_core.llm.base import LLMMessage
from docforge_core.llm.mock_provider import MockLLMProvider


def _candidate(index: int = 0) -> dict[str, Any]:
    return {
        "candidate_index": index,
        "name": "三维模型导入与查看",
        "description": "三维模型导入与查看",
        "capability_type": "three_d_model_management",
        "implementation_status": "current",
        "supporting_evidence_ids": ["ev_product"],
        "supporting_quotes": ["当前版本支持三维模型导入与查看"],
    }


def _result(supported: bool) -> dict[str, Any]:
    return {
        "candidate_index": 0,
        "supported": supported,
        "name_supported": supported,
        "capability_type_supported": supported,
        "implementation_status_supported": supported,
        "corrected_capability_type": None,
        "corrected_implementation_status": None,
        "reason": "semantic result",
    }


def test_empty_candidates_return_empty_without_llm_call() -> None:
    provider = MockLLMProvider(json_response={"results": []})
    verifier = ProductCapabilityGroundingVerifier(provider)

    assert verifier.verify_candidates([], {}) == []
    assert provider.json_call_count == 0


def test_verifier_parses_supported_true() -> None:
    provider = MockLLMProvider(json_response={"results": [_result(True)]})

    result = ProductCapabilityGroundingVerifier(provider).verify_candidates(
        [_candidate()],
        {"ev_product": "当前版本支持三维模型导入与查看"},
    )

    assert result[0]["supported"] is True
    assert provider.json_call_count == 1


def test_verifier_parses_supported_false() -> None:
    provider = MockLLMProvider(json_response={"results": [_result(False)]})

    result = ProductCapabilityGroundingVerifier(provider).verify_candidates(
        [_candidate()],
        {"ev_product": "当前版本支持三维模型导入与查看"},
    )

    assert result[0]["supported"] is False


def test_verifier_missing_results_fail_closed() -> None:
    provider = MockLLMProvider(json_response={})

    result = ProductCapabilityGroundingVerifier(provider).verify_candidates(
        [_candidate()],
        {"ev_product": "当前版本支持三维模型导入与查看"},
    )

    assert result[0]["supported"] is False
    assert "fail closed" in result[0]["reason"]


def test_verifier_missing_candidate_result_fail_closed() -> None:
    provider = MockLLMProvider(json_response={"results": []})

    result = ProductCapabilityGroundingVerifier(provider).verify_candidates(
        [_candidate()],
        {"ev_product": "当前版本支持三维模型导入与查看"},
    )

    assert result[0]["supported"] is False
    assert "未返回" in result[0]["reason"]


def test_verifier_json_failure_fails_closed() -> None:
    class FailingProvider(MockLLMProvider):
        def generate_json(
            self,
            messages: list[LLMMessage],
            temperature: float = 0.1,
            max_tokens: int | None = None,
        ) -> dict[str, Any]:
            raise ValueError("bad verifier json")

    result = ProductCapabilityGroundingVerifier(FailingProvider()).verify_candidates(
        [_candidate()],
        {"ev_product": "当前版本支持三维模型导入与查看"},
    )

    assert result[0]["supported"] is False
    assert "verifier 解析失败" in result[0]["reason"]


def test_verifier_preserves_corrections() -> None:
    correction = _result(True)
    correction.update(
        {
            "capability_type_supported": False,
            "implementation_status_supported": False,
            "corrected_capability_type": "three_d_model_management",
            "corrected_implementation_status": "planned",
        }
    )
    provider = MockLLMProvider(json_response={"results": [correction]})

    result = ProductCapabilityGroundingVerifier(provider).verify_candidates(
        [_candidate()],
        {"ev_product": "未来规划支持三维模型导入与查看"},
    )

    assert result[0]["corrected_capability_type"] == "three_d_model_management"
    assert result[0]["corrected_implementation_status"] == "planned"
