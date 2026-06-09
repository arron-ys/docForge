"""Shared evidence-binding policy for capability-related outline sections."""

from dataclasses import dataclass
from typing import Any

from docforge_core.domain.schemas import FrozenDocPlan

from .title_safety import normalize_title


@dataclass(frozen=True)
class SectionEvidenceAssessment:
    """Expected evidence bindings derived only from a locked plan."""

    is_capability_related: bool
    capability_evidence_ids: frozenset[str]
    fact_evidence_ids: frozenset[str]
    unresolved_capability_ids: frozenset[str]
    unresolved_fact_ids: frozenset[str]
    unresolved_title_match: bool

    @property
    def expected_evidence_ids(self) -> frozenset[str]:
        return self.capability_evidence_ids | self.fact_evidence_ids


def is_capability_related_section(
    section_title: str,
    required_capability_ids: list[str],
    required_fact_ids: list[str],
    allowed_current_feature_names: list[str],
    current_capabilities: list[dict[str, Any]],
    current_facts: list[dict[str, Any]],
) -> bool:
    """Recognize capability sections without using an untrusted keyword library."""

    if required_capability_ids or required_fact_ids:
        return True
    normalized_title = normalize_title(section_title)
    if not normalized_title:
        return False
    trusted_names = [
        *allowed_current_feature_names,
        *(str(item.get("name", "")) for item in current_capabilities),
        *(str(item.get("content", "")) for item in current_facts),
    ]
    return any(
        normalized_name and normalized_name in normalized_title
        for normalized_name in (normalize_title(name) for name in trusted_names)
    )


def assess_section_evidence(
    section: dict[str, Any],
    frozen_doc_plan: FrozenDocPlan,
) -> SectionEvidenceAssessment:
    """Resolve the exact product evidence a section must bind."""

    current_capabilities = frozen_doc_plan.feature_policy.get(
        "current_capabilities", []
    )
    current_facts = frozen_doc_plan.feature_policy.get("current_facts", [])
    allowed_names = frozen_doc_plan.feature_policy.get(
        "allowed_current_feature_names", []
    )
    required_capability_ids = _string_list(section.get("required_capability_ids"))
    required_fact_ids = _string_list(section.get("required_fact_ids"))
    section_title = str(section.get("title", ""))

    capability_evidence = _capability_evidence_map(frozen_doc_plan)
    fact_evidence = _fact_evidence_map(current_facts, capability_evidence)
    title_capability_ids = _matching_ids(
        section_title, current_capabilities, "capability_id", "name"
    )
    title_fact_ids = _matching_ids(section_title, current_facts, "fact_id", "content")

    capability_ids = set(required_capability_ids) | title_capability_ids
    fact_ids = set(required_fact_ids) | title_fact_ids
    capability_expected = {
        evidence_id
        for capability_id in capability_ids
        for evidence_id in capability_evidence.get(capability_id, set())
    }
    fact_expected = {
        evidence_id
        for fact_id in fact_ids
        for evidence_id in fact_evidence.get(fact_id, set())
    }
    related = is_capability_related_section(
        section_title,
        required_capability_ids,
        required_fact_ids,
        allowed_names,
        current_capabilities,
        current_facts,
    )
    title_matches_allowed = _matches_any(section_title, allowed_names)

    return SectionEvidenceAssessment(
        is_capability_related=related,
        capability_evidence_ids=frozenset(capability_expected),
        fact_evidence_ids=frozenset(fact_expected),
        unresolved_capability_ids=frozenset(
            item for item in capability_ids if not capability_evidence.get(item)
        ),
        unresolved_fact_ids=frozenset(
            item for item in fact_ids if not fact_evidence.get(item)
        ),
        unresolved_title_match=bool(
            title_matches_allowed
            and not title_capability_ids
            and not title_fact_ids
        ),
    )


def _capability_evidence_map(plan: FrozenDocPlan) -> dict[str, set[str]]:
    result: dict[str, set[str]] = {}
    for item in plan.evidence_policy.get("evidence_trace", []):
        capability_id = str(item.get("capability_id", ""))
        evidence_id = str(item.get("evidence_id", ""))
        if capability_id and evidence_id:
            result.setdefault(capability_id, set()).add(evidence_id)
    return result


def _fact_evidence_map(
    current_facts: list[dict[str, Any]],
    capability_evidence: dict[str, set[str]],
) -> dict[str, set[str]]:
    result: dict[str, set[str]] = {}
    for fact in current_facts:
        fact_id = str(fact.get("fact_id", ""))
        if not fact_id:
            continue
        direct_ids = set(_string_list(fact.get("supporting_evidence_ids")))
        if direct_ids:
            result[fact_id] = direct_ids
            continue
        if fact_id.startswith("fact_"):
            result[fact_id] = set(capability_evidence.get(fact_id.removeprefix("fact_"), set()))
    return result


def _matching_ids(
    title: str,
    items: list[dict[str, Any]],
    id_field: str,
    name_field: str,
) -> set[str]:
    normalized_title = normalize_title(title)
    return {
        str(item[id_field])
        for item in items
        if item.get(id_field)
        and normalize_title(str(item.get(name_field, "")))
        and normalize_title(str(item.get(name_field, ""))) in normalized_title
    }


def _matches_any(title: str, names: list[str]) -> bool:
    normalized_title = normalize_title(title)
    return any(
        normalized_name and normalized_name in normalized_title
        for normalized_name in (normalize_title(name) for name in names)
    )


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if item]
