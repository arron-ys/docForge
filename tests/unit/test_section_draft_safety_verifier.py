import pytest

from docforge_core.agents.section_draft_safety_verifier import SectionDraftSafetyVerifier
from docforge_core.llm.base import LLMMessage, LLMProvider, LLMResponse


class FakeSafetyProvider(LLMProvider):
    def __init__(self, response=None, exc: Exception | None = None) -> None:
        self.response = response
        self.exc = exc
        self.messages: list[list[LLMMessage]] = []

    def generate_text(
        self,
        messages: list[LLMMessage],
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        raise NotImplementedError("tests call generate_json directly")

    def generate_json(
        self,
        messages: list[LLMMessage],
        temperature: float = 0.1,
        max_tokens: int | None = None,
    ):
        self.messages.append(messages)
        if self.exc is not None:
            raise self.exc
        return self.response


def _verify(response=None, exc: Exception | None = None) -> None:
    SectionDraftSafetyVerifier(FakeSafetyProvider(response=response, exc=exc)).verify(
        section_draft={
            "content": "当前版本明确支持数据集管理能力。",
            "citations": [{"evidence_id": "ev_product", "quote": "当前版本明确支持数据集管理能力"}],
        },
        section_plan_payload={
            "section_id": "sec_001_001",
            "required_evidence_ids": ["ev_product"],
        },
        evidence_bundle=[
            {
                "evidence_id": "ev_product",
                "quote": "当前版本明确支持数据集管理能力",
                "summary": "当前版本明确支持数据集管理能力",
                "extracted_facts": [],
            }
        ],
        writing_style_payload={"reference_style_usage_rule": "不得作为产品事实"},
    )


def test_section_draft_safety_verifier_accepts_safe_output() -> None:
    _verify(
        {
            "safe": True,
            "risk_type": "none",
            "reason": "",
            "offending_spans": [],
        }
    )


@pytest.mark.parametrize(
    "risk_type",
    [
        "reference_style_as_fact",
        "evidence_bypass",
        "unsupported_fact_source",
    ],
)
def test_section_draft_safety_verifier_rejects_unsafe_output(risk_type: str) -> None:
    with pytest.raises(ValueError, match=risk_type):
        _verify(
            {
                "safe": False,
                "risk_type": risk_type,
                "reason": "unsafe",
                "offending_spans": ["unsafe span"],
            }
        )


def test_section_draft_safety_verifier_fails_closed_on_malformed_json() -> None:
    with pytest.raises(ValueError, match="fail closed"):
        _verify(exc=ValueError("not json"))


def test_section_draft_safety_verifier_rejects_safe_true_with_non_none_risk_type() -> None:
    with pytest.raises(ValueError, match="safe=true"):
        _verify(
            {
                "safe": True,
                "risk_type": "reference_style_as_fact",
                "reason": "contradictory",
                "offending_spans": [],
            }
        )


def test_section_draft_safety_verifier_rejects_safe_false_with_none_risk_type() -> None:
    with pytest.raises(ValueError, match="safe=false"):
        _verify(
            {
                "safe": False,
                "risk_type": "none",
                "reason": "contradictory",
                "offending_spans": [],
            }
        )


def test_section_draft_safety_verifier_rejects_bad_offending_spans() -> None:
    with pytest.raises(ValueError, match=r"offending_spans 必须是 list\[str\]"):
        _verify(
            {
                "safe": True,
                "risk_type": "none",
                "reason": "",
                "offending_spans": ["ok", {"bad": "span"}],
            }
        )


def test_section_draft_safety_verifier_rejects_bad_reason() -> None:
    with pytest.raises(ValueError, match="reason 必须是 str"):
        _verify(
            {
                "safe": True,
                "risk_type": "none",
                "reason": {"bad": "reason"},
                "offending_spans": [],
            }
        )
