"""Semantic safety verifier for Writer-facing plan fields."""

from __future__ import annotations

import json
from typing import Any, Protocol

from docforge_core.llm.base import LLMMessage, LLMProvider
from docforge_core.llm.prompt_loader import load_prompt

from .writing_goal_safety import contains_unsafe_instruction

SAFE_RISK_TYPES = {
    "none",
    "evidence_bypass",
    "reference_as_fact",
    "constraint_bypass",
    "free_generation",
    "fabrication",
    "future_as_current",
    "body_generation",
    "unknown",
}
VALID_RISK_TYPES = SAFE_RISK_TYPES
FAIL_CLOSED_REASON = "writing plan safety verifier failed closed"
MISSING_LLM_PROVIDER_REASON = "writing plan safety verifier missing llm provider"
INCONSISTENT_SAFE_REASON = "writing plan safety verifier returned inconsistent safe result"
INVALID_RISK_TYPE_REASON = "writing plan safety verifier returned invalid risk_type"


class WritingPlanSafetyVerifierProtocol(Protocol):
    def verify_items(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Return one safety verdict for each collected item."""


class WritingPlanSafetyVerifier:
    """Batch-check plan fields for instructions that could pollute WriterAgent."""

    def __init__(self, llm_provider: LLMProvider | None = None) -> None:
        self.llm_provider = llm_provider

    def verify_items(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not items:
            return []
        hard_denied = {
            item.get("item_index"): self._hard_deny_result(item)
            for item in items
            if contains_unsafe_instruction(str(item.get("text", "")))
        }
        pending_items = [
            item for item in items if item.get("item_index") not in hard_denied
        ]
        if not pending_items:
            return [
                hard_denied.get(item.get("item_index"))
                or self._unsafe_result(item.get("item_index"), "unknown", FAIL_CLOSED_REASON)
                for item in items
            ]
        if self.llm_provider is None:
            missing_provider = {
                item.get("item_index"): self._unsafe_result(
                    item.get("item_index"),
                    "unknown",
                    MISSING_LLM_PROVIDER_REASON,
                )
                for item in pending_items
            }
            return [
                hard_denied.get(item.get("item_index"))
                or missing_provider.get(item.get("item_index"))
                or self._unsafe_result(item.get("item_index"), "unknown", FAIL_CLOSED_REASON)
                for item in items
            ]

        try:
            raw = self.llm_provider.generate_json(
                [
                    LLMMessage(
                        role="system",
                        content=load_prompt("writing_plan_safety_verifier.md"),
                    ),
                    LLMMessage(
                        role="user",
                        content=json.dumps({"items": pending_items}, ensure_ascii=False, indent=2),
                    ),
                ]
            )
        except Exception:
            llm_results = {
                item.get("item_index"): self._unsafe_result(
                    item.get("item_index"),
                    "unknown",
                    FAIL_CLOSED_REASON,
                )
                for item in pending_items
            }
            return self._merge_results(items, hard_denied, llm_results)

        results = raw.get("results")
        if not isinstance(results, list):
            llm_results = {
                item.get("item_index"): self._unsafe_result(
                    item.get("item_index"),
                    "unknown",
                    FAIL_CLOSED_REASON,
                )
                for item in pending_items
            }
            return self._merge_results(items, hard_denied, llm_results)

        by_index: dict[int, dict[str, Any]] = {}
        malformed = False
        pending_indexes = {
            item.get("item_index") for item in pending_items if isinstance(item.get("item_index"), int)
        }
        for result in results:
            if not isinstance(result, dict):
                malformed = True
                continue
            item_index = result.get("item_index")
            if (
                not isinstance(item_index, int)
                or item_index not in pending_indexes
                or item_index in by_index
            ):
                malformed = True
                continue
            by_index[item_index] = result
        if malformed:
            return self._fail_closed(items)
        verified: list[dict[str, Any]] = []
        for item in pending_items:
            item_index = item.get("item_index")
            if not isinstance(item_index, int):
                verified.append(self._unsafe_result(item_index, "unknown", FAIL_CLOSED_REASON))
                continue
            result = by_index.get(item_index)
            if not isinstance(result, dict):
                verified.append(self._unsafe_result(item_index, "unknown", FAIL_CLOSED_REASON))
                continue
            if "safe" not in result:
                verified.append(self._unsafe_result(item_index, "unknown", FAIL_CLOSED_REASON))
                continue
            safe = result.get("safe") is True
            risk_type, risk_type_valid = self._normalize_risk_type(
                result.get("risk_type"),
                safe=safe,
            )
            if safe and not risk_type_valid:
                verified.append(
                    self._unsafe_result(item_index, "unknown", INVALID_RISK_TYPE_REASON)
                )
                continue
            if safe and risk_type != "none":
                verified.append(
                    self._unsafe_result(item_index, "unknown", INCONSISTENT_SAFE_REASON)
                )
                continue
            reason = str(result.get("reason") or ("safe" if safe else FAIL_CLOSED_REASON))
            verified.append(
                {
                    "item_index": item_index,
                    "safe": safe,
                    "risk_type": risk_type,
                    "reason": reason,
                }
            )
        llm_results = {item["item_index"]: item for item in verified}
        return self._merge_results(items, hard_denied, llm_results)

    @staticmethod
    def _normalize_risk_type(value: object, *, safe: bool) -> tuple[str, bool]:
        if value is None:
            return ("none" if safe else "unknown", True)
        if not isinstance(value, str):
            return ("unknown", False)
        normalized = value.strip().lower()
        if not normalized:
            return ("none" if safe else "unknown", True)
        if normalized in VALID_RISK_TYPES:
            return (normalized, True)
        return ("unknown", False)

    @staticmethod
    def _unsafe_result(item_index: object, risk_type: str, reason: str) -> dict[str, Any]:
        return {
            "item_index": item_index if isinstance(item_index, int) else -1,
            "safe": False,
            "risk_type": risk_type,
            "reason": reason,
        }

    @classmethod
    def _hard_deny_result(cls, item: dict[str, Any]) -> dict[str, Any]:
        return cls._unsafe_result(
            item.get("item_index"),
            "unknown",
            "deterministic hard-deny matched unsafe writing instruction",
        )

    @classmethod
    def _merge_results(
        cls,
        items: list[dict[str, Any]],
        hard_denied: dict[object, dict[str, Any]],
        llm_results: dict[object, dict[str, Any]],
    ) -> list[dict[str, Any]]:
        return [
            hard_denied.get(item.get("item_index"))
            or llm_results.get(item.get("item_index"))
            or cls._unsafe_result(item.get("item_index"), "unknown", FAIL_CLOSED_REASON)
            for item in items
        ]

    @classmethod
    def _fail_closed(cls, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            cls._unsafe_result(item.get("item_index"), "unknown", FAIL_CLOSED_REASON)
            for item in items
        ]
