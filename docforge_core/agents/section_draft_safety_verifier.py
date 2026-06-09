"""Narrow semantic safety verifier for WriterAgent section drafts."""

from __future__ import annotations

import json
from typing import Any

from docforge_core.llm.base import LLMMessage, LLMProvider
from docforge_core.llm.prompt_loader import load_prompt

VALID_SECTION_DRAFT_SAFETY_RISK_TYPES = {
    "none",
    "reference_style_as_fact",
    "evidence_bypass",
    "unsupported_fact_source",
    "malformed_output",
}


class SectionDraftSafetyVerifier:
    """Fail-closed semantic check for reference-style-as-fact contamination."""

    def __init__(self, llm_provider: LLMProvider | None) -> None:
        self.llm_provider = llm_provider

    def verify(
        self,
        section_draft: dict[str, Any],
        section_plan_payload: dict[str, Any],
        evidence_bundle: list[dict[str, Any]],
        writing_style_payload: dict[str, Any],
    ) -> None:
        if self.llm_provider is None:
            raise ValueError("SectionDraftSafetyVerifier 要求 llm_provider")
        payload = {
            "section_draft": {
                "content": section_draft.get("content", ""),
                "citations": section_draft.get("citations", []),
            },
            "section_plan": section_plan_payload,
            "evidence_bundle": [
                {
                    "evidence_id": item.get("evidence_id", ""),
                    "quote": item.get("quote", ""),
                    "summary": item.get("summary", ""),
                    "extracted_facts": item.get("extracted_facts", []),
                }
                for item in evidence_bundle
            ],
            "writing_style_summary": writing_style_payload,
        }
        try:
            result = self.llm_provider.generate_json(
                [
                    LLMMessage(
                        role="system",
                        content=load_prompt("section_draft_safety_verifier.md"),
                    ),
                    LLMMessage(
                        role="user",
                        content=json.dumps(payload, ensure_ascii=False, indent=2),
                    ),
                ]
            )
        except Exception as exc:
            raise ValueError("SectionDraftSafetyVerifier fail closed") from exc
        self._validate_result(result)

    @staticmethod
    def _validate_result(result: dict[str, Any]) -> None:
        if not isinstance(result, dict):
            raise ValueError("SectionDraftSafetyVerifier 输出必须是对象")
        safe = result.get("safe")
        risk_type = result.get("risk_type")
        reason = result.get("reason")
        offending_spans = result.get("offending_spans")
        if not isinstance(safe, bool):
            raise ValueError("SectionDraftSafetyVerifier safe 必须是 bool")
        if risk_type not in VALID_SECTION_DRAFT_SAFETY_RISK_TYPES:
            raise ValueError("SectionDraftSafetyVerifier risk_type 不合法")
        if not isinstance(reason, str):
            raise ValueError("SectionDraftSafetyVerifier reason 必须是 str")
        if not isinstance(offending_spans, list) or any(
            not isinstance(item, str) for item in offending_spans
        ):
            raise ValueError("SectionDraftSafetyVerifier offending_spans 必须是 list[str]")
        if safe and risk_type != "none":
            raise ValueError("SectionDraftSafetyVerifier safe=true 时 risk_type 必须是 none")
        if not safe and risk_type == "none":
            raise ValueError("SectionDraftSafetyVerifier safe=false 时 risk_type 不得是 none")
        if not safe:
            raise ValueError(f"SectionDraftSafetyVerifier unsafe: {risk_type}")
