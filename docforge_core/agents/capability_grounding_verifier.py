"""LLM-based semantic grounding verification for product capability claims."""

from __future__ import annotations

import json
from typing import Any

from docforge_core.llm.base import LLMMessage, LLMProvider
from docforge_core.llm.prompt_loader import load_prompt
from docforge_core.llm.provider_factory import create_llm_provider


class ProductCapabilityGroundingVerifier:
    """Verify that source-grounded quotes semantically support candidate claims."""

    def __init__(self, llm_provider: LLMProvider | None = None) -> None:
        self.llm_provider = llm_provider or create_llm_provider()

    def verify_candidates(
        self,
        candidates: list[dict[str, Any]],
        evidence_text_by_id: dict[str, str],
    ) -> list[dict[str, Any]]:
        if not candidates:
            return []

        try:
            response = self.llm_provider.generate_json(
                [
                    LLMMessage(
                        role="system",
                        content=load_prompt("product_capability_verifier.md"),
                    ),
                    LLMMessage(
                        role="user",
                        content=json.dumps(
                            {
                                "candidates": candidates,
                                "evidence_text_by_id": evidence_text_by_id,
                            },
                            ensure_ascii=False,
                            indent=2,
                        ),
                    ),
                ]
            )
            raw_results = response.get("results")
            if not isinstance(raw_results, list):
                raise ValueError("verifier 输出缺少 results 列表")
        except Exception as exc:
            return [
                self._unsupported_result(
                    self._candidate_index(candidate, fallback=index),
                    f"verifier 解析失败，已 fail closed: {exc}",
                )
                for index, candidate in enumerate(candidates)
            ]

        parsed_by_index: dict[int, dict[str, Any]] = {}
        for raw in raw_results:
            if not isinstance(raw, dict):
                continue
            candidate_index = raw.get("candidate_index")
            if not isinstance(candidate_index, int):
                continue
            parsed_by_index[candidate_index] = self._normalize_result(raw)

        results: list[dict[str, Any]] = []
        for index, candidate in enumerate(candidates):
            candidate_index = self._candidate_index(candidate, fallback=index)
            results.append(
                parsed_by_index.get(
                    candidate_index,
                    self._unsupported_result(
                        candidate_index,
                        "verifier 未返回该 candidate 的结果，已 fail closed。",
                    ),
                )
            )
        return results

    @staticmethod
    def _candidate_index(candidate: dict[str, Any], fallback: int) -> int:
        value = candidate.get("candidate_index")
        return value if isinstance(value, int) else fallback

    @staticmethod
    def _normalize_result(raw: dict[str, Any]) -> dict[str, Any]:
        return {
            "candidate_index": raw["candidate_index"],
            "supported": raw.get("supported") is True,
            "name_supported": raw.get("name_supported") is True,
            "capability_type_supported": raw.get("capability_type_supported") is True,
            "implementation_status_supported": (
                raw.get("implementation_status_supported") is True
            ),
            "corrected_capability_type": raw.get("corrected_capability_type"),
            "corrected_implementation_status": raw.get(
                "corrected_implementation_status"
            ),
            "reason": str(raw.get("reason", "")).strip() or "verifier 未提供判断理由。",
        }

    @staticmethod
    def _unsupported_result(candidate_index: int, reason: str) -> dict[str, Any]:
        return {
            "candidate_index": candidate_index,
            "supported": False,
            "name_supported": False,
            "capability_type_supported": False,
            "implementation_status_supported": False,
            "corrected_capability_type": None,
            "corrected_implementation_status": None,
            "reason": reason,
        }
