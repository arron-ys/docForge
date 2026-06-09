import pytest

from docforge_core.agents.capability_validation_trace import (
    build_capability_claim_hash,
    build_capability_validation_trace,
    build_evidence_supports_hash,
    validate_capability_trace,
)
from docforge_core.domain.enums import (
    CapabilityType,
    ImplementationStatus,
    ValidationStatus,
)
from docforge_core.domain.schemas import EvidenceSupport, ProductCapability


def _capability() -> ProductCapability:
    capability = ProductCapability(
        capability_id="cap_trace",
        name="数据集管理",
        capability_type=CapabilityType.DATASET_MANAGEMENT,
        implementation_status=ImplementationStatus.CURRENT,
        validation_status=ValidationStatus.VALIDATED,
        evidence_supports=[
            EvidenceSupport(
                evidence_id="ev_product",
                source_id="product_source",
                quote="当前版本明确支持数据集管理能力",
            )
        ],
    )
    capability.validation_trace = build_capability_validation_trace(
        capability,
        {
            "supported": True,
            "name_supported": True,
            "capability_type_supported": True,
            "implementation_status_supported": True,
            "reason": "语义支持",
        },
    )
    return capability


def test_claim_hash_is_stable_for_same_input() -> None:
    first = build_capability_claim_hash(
        "数据集管理",
        CapabilityType.DATASET_MANAGEMENT,
        ImplementationStatus.CURRENT,
        ValidationStatus.VALIDATED,
    )
    second = build_capability_claim_hash(
        "数据集管理",
        CapabilityType.DATASET_MANAGEMENT,
        ImplementationStatus.CURRENT,
        ValidationStatus.VALIDATED,
    )

    assert first == second


def test_evidence_supports_hash_is_order_insensitive() -> None:
    first = EvidenceSupport(evidence_id="ev_1", source_id="src_1", quote="当前版本支持能力一")
    second = EvidenceSupport(evidence_id="ev_2", source_id="src_2", quote="当前版本支持能力二")

    assert build_evidence_supports_hash([first, second]) == build_evidence_supports_hash(
        [second, first]
    )


def test_validate_capability_trace_accepts_valid_capability() -> None:
    validate_capability_trace(_capability())


def test_validate_capability_trace_rejects_missing_trace() -> None:
    capability = _capability()
    capability.validation_trace = None

    with pytest.raises(ValueError, match="validation_trace"):
        validate_capability_trace(capability)


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("name", "AI模型训练"),
        ("capability_type", CapabilityType.AI_TRAINING),
        ("implementation_status", ImplementationStatus.PLANNED),
    ],
)
def test_validate_capability_trace_rejects_tampered_claim(
    field_name: str,
    value: object,
) -> None:
    capability = _capability()
    setattr(capability, field_name, value)

    with pytest.raises(ValueError, match="claim_hash"):
        validate_capability_trace(capability)


def test_validate_capability_trace_rejects_tampered_support_quote() -> None:
    capability = _capability()
    capability.evidence_supports[0].quote = "另一个真实但未验证的引用文本"

    with pytest.raises(ValueError, match="evidence_supports_hash"):
        validate_capability_trace(capability)


def test_validate_capability_trace_rejects_semantic_grounded_false() -> None:
    capability = _capability()
    assert capability.validation_trace is not None
    capability.validation_trace.semantic_grounded = False

    with pytest.raises(ValueError, match="semantic_grounded"):
        validate_capability_trace(capability)


def test_validate_capability_trace_rejects_source_grounded_false() -> None:
    capability = _capability()
    assert capability.validation_trace is not None
    capability.validation_trace.source_grounded = False

    with pytest.raises(ValueError, match="source_grounded"):
        validate_capability_trace(capability)


def test_validate_capability_trace_rejects_name_supported_false() -> None:
    capability = _capability()
    assert capability.validation_trace is not None
    capability.validation_trace.name_supported = False

    with pytest.raises(ValueError, match="name_supported"):
        validate_capability_trace(capability)


def test_validate_capability_trace_rejects_unknown_validator_name() -> None:
    capability = _capability()
    assert capability.validation_trace is not None
    capability.validation_trace.validator_name = "UnknownVerifier"

    with pytest.raises(ValueError, match="validator_name"):
        validate_capability_trace(capability)
