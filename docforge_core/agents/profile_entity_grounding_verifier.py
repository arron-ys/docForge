"""LLM-based semantic grounding verification for ProductProfile entities."""

from __future__ import annotations

import json
from typing import Any

from docforge_core.llm.base import LLMMessage, LLMProvider
from docforge_core.llm.prompt_loader import load_prompt
from docforge_core.llm.provider_factory import create_llm_provider


class ProductProfileEntityGroundingVerifier:
    """Verify that quotes semantically support auxiliary ProductProfile entities."""

    def __init__(self, llm_provider: LLMProvider | None = None) -> None:
        self.llm_provider = llm_provider or create_llm_provider()

    def verify_entities(
        self,
        entities: list[dict[str, Any]],
        evidence_text_by_id: dict[str, str],
    ) -> list[dict[str, Any]]:
        if not entities:
            return []

        try:
            response = self.llm_provider.generate_json(
                [
                    LLMMessage(
                        role="system",
                        content=load_prompt("profile_entity_verifier.md"),
                    ),
                    LLMMessage(
                        role="user",
                        content=json.dumps(
                            {
                                "entities": entities,
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
                raise ValueError("profile entity verifier 输出缺少 results 列表")
        except Exception as exc:
            return [
                self._unsupported_result(
                    self._entity_index(entity, fallback=index),
                    f"profile entity verifier 解析失败，已 fail closed: {exc}",
                )
                for index, entity in enumerate(entities)
            ]

        parsed_by_index: dict[int, dict[str, Any]] = {}
        for raw in raw_results:
            if not isinstance(raw, dict):
                continue
            entity_index = raw.get("entity_index")
            if not isinstance(entity_index, int):
                continue
            parsed_by_index[entity_index] = self._normalize_result(raw)

        results: list[dict[str, Any]] = []
        for index, entity in enumerate(entities):
            entity_index = self._entity_index(entity, fallback=index)
            results.append(
                parsed_by_index.get(
                    entity_index,
                    self._unsupported_result(
                        entity_index,
                        "profile entity verifier 未返回该 entity 的结果，已 fail closed。",
                    ),
                )
            )
        return results

    @staticmethod
    def _entity_index(entity: dict[str, Any], fallback: int) -> int:
        value = entity.get("entity_index")
        return value if isinstance(value, int) else fallback

    @staticmethod
    def _normalize_result(raw: dict[str, Any]) -> dict[str, Any]:
        return {
            "entity_index": raw["entity_index"],
            "supported": raw.get("supported") is True,
            "name_supported": raw.get("name_supported") is True,
            "entity_type_supported": raw.get("entity_type_supported") is True,
            "implementation_status_supported": (
                raw.get("implementation_status_supported") is True
            ),
            "corrected_implementation_status": raw.get(
                "corrected_implementation_status"
            ),
            "reason": str(raw.get("reason", "")).strip()
            or "profile entity verifier 未提供判断理由。",
        }

    @staticmethod
    def _unsupported_result(entity_index: int, reason: str) -> dict[str, Any]:
        return {
            "entity_index": entity_index,
            "supported": False,
            "name_supported": False,
            "entity_type_supported": False,
            "implementation_status_supported": False,
            "corrected_implementation_status": None,
            "reason": reason,
        }
