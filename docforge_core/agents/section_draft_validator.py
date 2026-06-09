"""Validate WriterAgent section draft output before it reaches draft_v1.json."""

from __future__ import annotations

import json
from typing import Any

from docforge_core.domain.schemas import FrozenDocPlan, SectionPlan

from .title_safety import is_forbidden_title

ALLOWED_SECTION_DRAFT_FIELDS = {
    "section_id",
    "content",
    "evidence_ids_used",
    "citations",
    "warnings",
}
ALLOWED_CITATION_FIELDS = {"evidence_id", "quote"}
RESERVED_REFERENCE_TOKENS = {"reference_style", "style_only"}


class SectionDraftValidator:
    """Deterministic safety checks for one generated section draft."""

    def validate_section_draft(
        self,
        section_draft: dict[str, Any],
        section_plan: SectionPlan,
        evidence_bundle: list[dict[str, Any]],
        frozen_doc_plan: FrozenDocPlan,
    ) -> None:
        if not isinstance(section_draft, dict):
            raise ValueError("section_draft 必须是对象")
        self._reject_unknown_fields(section_draft)
        if section_draft.get("section_id") != section_plan.section_id:
            raise ValueError("section_draft section_id 不匹配")
        content = section_draft.get("content")
        if not isinstance(content, str) or not content.strip():
            raise ValueError("section_draft content 不得为空")
        forbidden = self._forbidden_feature_names(frozen_doc_plan)
        if is_forbidden_title(content, forbidden):
            raise ValueError("section_draft content 包含 forbidden feature")
        if any(token in content for token in RESERVED_REFERENCE_TOKENS):
            raise ValueError("section_draft content 包含 reference_style 内部保留词")

        evidence_ids_used = section_draft.get("evidence_ids_used")
        if not isinstance(evidence_ids_used, list) or not evidence_ids_used:
            raise ValueError("section_draft evidence_ids_used 不得为空")
        evidence_ids_used_set = {str(item) for item in evidence_ids_used if item}
        if len(evidence_ids_used_set) != len(evidence_ids_used):
            raise ValueError("section_draft evidence_ids_used 包含非法项")
        required_ids = set(section_plan.required_evidence_ids)
        if not evidence_ids_used_set.issubset(required_ids):
            raise ValueError("section_draft evidence_ids_used 超出 SectionPlan")

        bundle_by_id = {str(item.get("evidence_id", "")): item for item in evidence_bundle}
        if not evidence_ids_used_set.issubset(bundle_by_id.keys()):
            raise ValueError("section_draft evidence_ids_used 不在 evidence_bundle 中")
        reference_ids = set(
            frozen_doc_plan.evidence_policy.get("allowed_reference_style_ids", [])
        )
        if evidence_ids_used_set.intersection(reference_ids):
            raise ValueError("section_draft evidence_ids_used 包含 reference_style evidence")

        citations = section_draft.get("citations")
        if not isinstance(citations, list) or not citations:
            raise ValueError("section_draft citations 必须为非空列表")
        for citation in citations:
            if not isinstance(citation, dict):
                raise ValueError("section_draft citation 必须是对象")
            citation_keys = {key.strip() for key in citation if isinstance(key, str)}
            if len(citation_keys) != len(citation) or not citation_keys.issubset(
                ALLOWED_CITATION_FIELDS
            ):
                raise ValueError("section_draft citation 包含未允许字段")
            evidence_id = citation.get("evidence_id")
            quote = citation.get("quote")
            if (
                not isinstance(evidence_id, str)
                or not evidence_id.strip()
                or not isinstance(quote, str)
                or not quote.strip()
            ):
                raise ValueError("section_draft citation 缺少 evidence_id 或 quote")
            if evidence_id not in evidence_ids_used_set:
                raise ValueError("section_draft citation evidence_id 未被使用")
            if not self._quote_supported(quote, bundle_by_id[evidence_id]):
                raise ValueError("section_draft citation quote 不在 evidence_bundle 中")

        warnings = section_draft.get("warnings", [])
        if not isinstance(warnings, list) or any(
            not isinstance(item, str) for item in warnings
        ):
            raise ValueError("section_draft warnings 必须是字符串列表")

    @staticmethod
    def _reject_unknown_fields(section_draft: dict[str, Any]) -> None:
        keys = {key.strip() for key in section_draft if isinstance(key, str)}
        if len(keys) != len(section_draft) or not keys.issubset(
            ALLOWED_SECTION_DRAFT_FIELDS
        ):
            raise ValueError("section_draft 包含未允许字段")

    @staticmethod
    def _forbidden_feature_names(frozen_doc_plan: FrozenDocPlan) -> list[str]:
        raw = frozen_doc_plan.feature_policy.get("forbidden_as_current_feature_names", [])
        if not isinstance(raw, list):
            raise ValueError("forbidden_as_current_feature_names 必须是 list[str]")
        if any(not isinstance(item, str) or not item.strip() for item in raw):
            raise ValueError("forbidden_as_current_feature_names 必须是 list[str]")
        return raw

    @staticmethod
    def _quote_supported(quote: str, bundle_item: dict[str, Any]) -> bool:
        candidates = [
            str(bundle_item.get("quote", "")),
            str(bundle_item.get("summary", "")),
            json.dumps(bundle_item.get("extracted_facts", []), ensure_ascii=False),
        ]
        return any(quote in candidate for candidate in candidates if candidate)
