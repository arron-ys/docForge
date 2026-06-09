"""Stable validation credentials for evidence-grounded product capabilities."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from docforge_core.domain.enums import CapabilityType, ImplementationStatus, ValidationStatus
from docforge_core.domain.schemas import (
    CapabilityValidationTrace,
    EvidenceSupport,
    ProductCapability,
)

MAX_TRACE_REASON_LENGTH = 500
EXPECTED_VALIDATOR_NAME = "ProductCapabilityGroundingVerifier"


def _stable_hash(payload: Any) -> str:
    serialized = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def build_capability_claim_hash(
    name: str,
    capability_type: CapabilityType,
    implementation_status: ImplementationStatus,
    validation_status: ValidationStatus,
) -> str:
    return _stable_hash(
        {
            "name": name,
            "capability_type": capability_type.value,
            "implementation_status": implementation_status.value,
            "validation_status": validation_status.value,
        }
    )


def build_evidence_supports_hash(evidence_supports: list[EvidenceSupport]) -> str:
    supports = sorted(
        (
            {
                "evidence_id": support.evidence_id,
                "source_id": support.source_id,
                "quote": support.quote,
            }
            for support in evidence_supports
        ),
        key=lambda item: (item["evidence_id"], item["source_id"], item["quote"]),
    )
    return _stable_hash(supports)


def build_capability_validation_trace(
    capability: ProductCapability,
    verifier_result: dict[str, Any],
    source_grounded: bool = True,
) -> CapabilityValidationTrace:
    reason = str(verifier_result.get("reason", "")).strip() or None
    if reason is not None:
        reason = reason[:MAX_TRACE_REASON_LENGTH]
    return CapabilityValidationTrace(
        source_grounded=source_grounded,
        semantic_grounded=True,
        verifier_supported=verifier_result.get("supported") is True,
        name_supported=verifier_result.get("name_supported") is True,
        capability_type_supported=verifier_result.get("capability_type_supported") is True,
        implementation_status_supported=(
            verifier_result.get("implementation_status_supported") is True
        ),
        claim_hash=build_capability_claim_hash(
            capability.name,
            capability.capability_type,
            capability.implementation_status,
            capability.validation_status,
        ),
        evidence_supports_hash=build_evidence_supports_hash(
            capability.evidence_supports
        ),
        reason=reason,
    )


def validate_capability_trace(capability: ProductCapability) -> None:
    trace = capability.validation_trace
    if trace is None:
        raise ValueError("current capability 缺少 validation_trace")
    if not trace.source_grounded:
        raise ValueError("capability validation_trace source_grounded 必须为 true")
    if not trace.semantic_grounded:
        raise ValueError("capability validation_trace semantic_grounded 必须为 true")
    if not trace.verifier_supported:
        raise ValueError("capability validation_trace verifier_supported 必须为 true")
    if not trace.name_supported:
        raise ValueError("capability validation_trace name_supported 必须为 true")
    if trace.validator_name != EXPECTED_VALIDATOR_NAME:
        raise ValueError("capability validation_trace validator_name 不合法")

    claim_hash = build_capability_claim_hash(
        capability.name,
        capability.capability_type,
        capability.implementation_status,
        capability.validation_status,
    )
    if trace.claim_hash != claim_hash:
        raise ValueError("capability validation_trace claim_hash 不匹配")

    supports_hash = build_evidence_supports_hash(capability.evidence_supports)
    if trace.evidence_supports_hash != supports_hash:
        raise ValueError("capability validation_trace evidence_supports_hash 不匹配")
