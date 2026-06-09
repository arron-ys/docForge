from typing import Any

import pytest
from pydantic import ValidationError

from docforge_core.domain import constants
from docforge_core.domain.enums import (
    AllowedUsage,
    CapabilityType,
    CorpusType,
    DraftVersionLabel,
    EvidenceStrength,
    EvidenceType,
    FileType,
    ImplementationStatus,
    MissingInformationStatus,
    ScreenshotBindingStatus,
    SourceType,
    ValidationStatus,
)
from docforge_core.domain.schemas import (
    DocForgeState,
    DraftVersion,
    EvidenceItem,
    EvidenceSupport,
    MissingInformationItem,
    ProductCapability,
    ScreenshotBinding,
    SectionPlan,
    SourceItem,
    TemplateConfirmationDecision,
)
from docforge_core.parsers import (
    DocxParser,
    ImageParser,
    MarkdownParser,
    ParsedChunk,
    PdfParser,
    TextParser,
)


def _reference_evidence(**updates: object) -> EvidenceItem:
    data: dict[str, Any] = {
        "source_id": "src_ref",
        "source_type": SourceType.REFERENCE_SOFT_COPYRIGHT_DOC,
        "file_type": FileType.DOCX,
        "evidence_type": EvidenceType.REFERENCE_STYLE_ONLY,
        "corpus_type": CorpusType.REFERENCE_STYLE,
        "allowed_usage": AllowedUsage.STYLE_ONLY,
        "evidence_strength": EvidenceStrength.NOT_ALLOWED_AS_FACT,
    }
    data.update(updates)
    return EvidenceItem.model_validate(data)


def _product_evidence(**updates: object) -> EvidenceItem:
    data: dict[str, Any] = {
        "source_id": "src_product",
        "source_type": SourceType.PRD,
        "file_type": FileType.PDF,
        "evidence_type": EvidenceType.PRODUCT_DOCUMENT,
        "corpus_type": CorpusType.PRODUCT_EVIDENCE,
        "allowed_usage": AllowedUsage.FACTUAL_EVIDENCE,
        "evidence_strength": EvidenceStrength.MEDIUM,
    }
    data.update(updates)
    return EvidenceItem.model_validate(data)


def _reference_source(**updates: object) -> SourceItem:
    data: dict[str, Any] = {
        "source_type": SourceType.REFERENCE_SOFT_COPYRIGHT_DOC,
        "file_type": FileType.DOCX,
        "corpus_type": CorpusType.REFERENCE_STYLE,
        "allowed_usage": AllowedUsage.STYLE_ONLY,
        "is_reference_source": True,
        "is_product_source": False,
    }
    data.update(updates)
    return SourceItem.model_validate(data)


def _product_source(**updates: object) -> SourceItem:
    data: dict[str, Any] = {
        "source_type": SourceType.PRD,
        "file_type": FileType.PDF,
        "corpus_type": CorpusType.PRODUCT_EVIDENCE,
        "allowed_usage": AllowedUsage.FACTUAL_EVIDENCE,
        "is_reference_source": False,
        "is_product_source": True,
    }
    data.update(updates)
    return SourceItem.model_validate(data)


def test_section_plan_backfills_legacy_level_two_path() -> None:
    plan = SectionPlan(
        chapter_title="软件概述",
        section_title="软件定位",
        writing_goal="说明软件定位。",
    )
    assert plan.section_path == ["软件概述", "软件定位"]


@pytest.mark.parametrize(
    ("updates", "message"),
    [
        ({"section_id": ""}, "section_id"),
        ({"chapter_title": ""}, "chapter_title"),
        ({"section_title": ""}, "section_title"),
        ({"writing_goal": ""}, "writing_goal"),
        ({"section_level": 4}, "section_level"),
        ({"section_level": 3, "section_path": []}, "section_path"),
    ],
)
def test_section_plan_rejects_invalid_contract(
    updates: dict[str, object],
    message: str,
) -> None:
    values: dict[str, object] = {
        "section_id": "sec_1",
        "chapter_title": "软件概述",
        "section_title": "软件定位",
        "section_path": ["软件概述", "软件定位"],
        "writing_goal": "说明软件定位。",
    }
    values.update(updates)
    with pytest.raises(ValidationError, match=message):
        SectionPlan.model_validate(values)


def test_product_evidence_source_must_be_product_source() -> None:
    with pytest.raises(ValidationError, match="is_product_source"):
        _product_source(is_product_source=False)


def test_reference_style_source_must_be_reference_source() -> None:
    with pytest.raises(ValidationError, match="is_reference_source"):
        _reference_source(is_reference_source=False)


def test_reference_style_source_cannot_be_product_source() -> None:
    with pytest.raises(ValidationError, match="is_product_source"):
        _reference_source(is_product_source=True)


def test_product_evidence_source_cannot_be_reference_source() -> None:
    with pytest.raises(ValidationError, match="is_reference_source"):
        _product_source(is_reference_source=True)


def test_reference_soft_copyright_doc_must_use_reference_corpus() -> None:
    with pytest.raises(ValidationError, match="reference_style"):
        _reference_source(
            corpus_type=CorpusType.PRODUCT_EVIDENCE,
            allowed_usage=AllowedUsage.FACTUAL_EVIDENCE,
            is_reference_source=False,
            is_product_source=True,
        )


def test_screenshot_source_must_use_product_corpus() -> None:
    with pytest.raises(ValidationError, match="product_evidence"):
        _reference_source(
            source_type=SourceType.SCREENSHOT,
            file_type=FileType.PNG,
        )


def test_screenshot_source_is_display_material_product_source() -> None:
    source = _product_source(
        source_type=SourceType.SCREENSHOT,
        file_type=FileType.PNG,
        allowed_usage=AllowedUsage.DISPLAY_MATERIAL_ONLY,
    )

    assert source.corpus_type == CorpusType.PRODUCT_EVIDENCE
    assert source.allowed_usage == AllowedUsage.DISPLAY_MATERIAL_ONLY
    assert source.is_product_source is True


def test_user_note_source_must_use_product_corpus() -> None:
    with pytest.raises(ValidationError, match="product_evidence"):
        _reference_source(
            source_type=SourceType.USER_NOTE,
            file_type=FileType.TXT,
        )


def test_prd_source_must_use_product_corpus() -> None:
    with pytest.raises(ValidationError, match="product_evidence"):
        _reference_source(source_type=SourceType.PRD)


def test_hld_source_must_use_product_corpus() -> None:
    with pytest.raises(ValidationError, match="product_evidence"):
        _reference_source(source_type=SourceType.HLD)


def test_product_intro_doc_source_must_use_product_corpus() -> None:
    with pytest.raises(ValidationError, match="product_evidence"):
        _reference_source(source_type=SourceType.PRODUCT_INTRO_DOC)


def test_detailed_design_doc_source_must_use_product_corpus() -> None:
    with pytest.raises(ValidationError, match="product_evidence"):
        _reference_source(source_type=SourceType.DETAILED_DESIGN_DOC)


def test_reference_evidence_cannot_use_factual_evidence() -> None:
    with pytest.raises(ValidationError, match="style_only"):
        _reference_evidence(allowed_usage=AllowedUsage.FACTUAL_EVIDENCE)


def test_reference_evidence_must_be_reference_style_only() -> None:
    with pytest.raises(ValidationError, match="reference_style_only"):
        _reference_evidence(evidence_type=EvidenceType.PRODUCT_DOCUMENT)


def test_reference_evidence_must_not_be_allowed_as_fact() -> None:
    with pytest.raises(ValidationError, match="not_allowed_as_fact"):
        _reference_evidence(evidence_strength=EvidenceStrength.MEDIUM)


def test_product_screenshot_must_come_from_screenshot_source() -> None:
    with pytest.raises(ValidationError, match="screenshot"):
        _product_evidence(evidence_type=EvidenceType.PRODUCT_SCREENSHOT)


def test_user_confirmation_must_come_from_user_note_source() -> None:
    with pytest.raises(ValidationError, match="user_note"):
        _product_evidence(evidence_type=EvidenceType.USER_CONFIRMATION)


def test_product_evidence_cannot_be_reference_style_only() -> None:
    with pytest.raises(ValidationError, match="reference_style_only"):
        _product_evidence(evidence_type=EvidenceType.REFERENCE_STYLE_ONLY)


def test_product_evidence_cannot_be_not_allowed_as_fact() -> None:
    with pytest.raises(ValidationError, match="not_allowed_as_fact"):
        _product_evidence(evidence_strength=EvidenceStrength.NOT_ALLOWED_AS_FACT)


def test_reference_style_only_evidence_must_use_reference_corpus() -> None:
    with pytest.raises(ValidationError, match="reference_style_only"):
        _product_evidence(evidence_type=EvidenceType.REFERENCE_STYLE_ONLY)


def test_product_document_evidence_must_use_product_corpus() -> None:
    with pytest.raises(ValidationError, match="reference_style_only"):
        _reference_evidence(evidence_type=EvidenceType.PRODUCT_DOCUMENT)


def test_product_screenshot_evidence_must_use_product_corpus() -> None:
    with pytest.raises(ValidationError, match="reference_style_only"):
        _reference_evidence(
            source_type=SourceType.SCREENSHOT,
            file_type=FileType.PNG,
            evidence_type=EvidenceType.PRODUCT_SCREENSHOT,
        )


def test_product_screenshot_evidence_is_display_material_not_fact() -> None:
    evidence = _product_evidence(
        source_type=SourceType.SCREENSHOT,
        file_type=FileType.PNG,
        evidence_type=EvidenceType.PRODUCT_SCREENSHOT,
        allowed_usage=AllowedUsage.DISPLAY_MATERIAL_ONLY,
        evidence_strength=EvidenceStrength.NOT_ALLOWED_AS_FACT,
    )

    assert evidence.corpus_type == CorpusType.PRODUCT_EVIDENCE
    assert evidence.allowed_usage == AllowedUsage.DISPLAY_MATERIAL_ONLY
    assert evidence.evidence_strength == EvidenceStrength.NOT_ALLOWED_AS_FACT


def test_user_confirmation_evidence_must_use_product_corpus() -> None:
    with pytest.raises(ValidationError, match="reference_style_only"):
        _reference_evidence(
            source_type=SourceType.USER_NOTE,
            file_type=FileType.TXT,
            evidence_type=EvidenceType.USER_CONFIRMATION,
        )


def test_parsed_chunk_metadata_defaults_are_independent() -> None:
    first = ParsedChunk(text="first")
    second = ParsedChunk(text="second")

    first.metadata["key"] = "value"

    assert second.metadata == {}
    assert first.metadata is not second.metadata


def test_parser_classes_can_be_imported() -> None:
    assert DocxParser().supported_suffixes == frozenset({".docx"})
    assert PdfParser().supported_suffixes == frozenset({".pdf"})
    assert MarkdownParser().supported_suffixes == frozenset({".md", ".markdown"})
    assert TextParser().supported_suffixes == frozenset({".txt"})
    assert ImageParser().supported_suffixes == frozenset({".png", ".jpg", ".jpeg", ".webp"})


def test_docforge_state_mvp_defaults() -> None:
    state = DocForgeState(run_id="20260605_010203_abcd")

    assert state.target_doc_type == "software_copyright_doc"
    assert state.user_goal == "生成软件著作权文档"
    assert state.output_requirements["output_format"] == "docx"
    assert state.output_requirements["export_pdf"] is False
    assert state.output_requirements["export_markdown"] is False
    assert state.project_id == f"proj_{state.run_id}"
    assert state.product_capabilities == []


def test_evidence_support_requires_quote_and_bounded_confidence() -> None:
    EvidenceSupport(evidence_id="ev_1", source_id="src_1", quote="明确产品能力", confidence=0.8)

    with pytest.raises(ValidationError):
        EvidenceSupport(evidence_id="ev_1", source_id="src_1", quote="")
    with pytest.raises(ValidationError):
        EvidenceSupport(evidence_id="ev_1", source_id="src_1", quote="   ")
    with pytest.raises(ValidationError):
        EvidenceSupport(evidence_id="ev_1", source_id="src_1", quote="明确产品能力", confidence=1.1)


def test_validated_current_capability_requires_evidence_support() -> None:
    with pytest.raises(ValidationError, match="evidence_supports"):
        ProductCapability(
            capability_id="cap_1",
            name="数据集管理",
            capability_type=CapabilityType.DATASET_MANAGEMENT,
            implementation_status=ImplementationStatus.CURRENT,
            validation_status=ValidationStatus.VALIDATED,
            confidence=0.9,
        )


def test_old_state_payload_without_product_capabilities_remains_readable() -> None:
    state = DocForgeState.model_validate({"run_id": "20260605_010203_abcd"})

    assert state.product_capabilities == []


def test_old_product_capability_without_validation_trace_remains_readable() -> None:
    state = DocForgeState.model_validate(
        {
            "run_id": "20260605_010203_abcd",
            "product_capabilities": [
                {
                    "capability_id": "cap_old",
                    "name": "旧能力",
                    "implementation_status": "planned",
                    "validation_status": "validated",
                }
            ],
        }
    )

    assert state.product_capabilities[0].validation_trace is None


def test_template_confirmation_decision_requires_top_level_chapters() -> None:
    with pytest.raises(ValidationError):
        TemplateConfirmationDecision(
            selected_base_template_id="TEMPLATE_WEB",
            selected_base_template_name="Web 模板",
            selected_top_level_chapters=[],
        )


def test_old_frozen_doc_plan_payload_remains_readable() -> None:
    state = DocForgeState.model_validate(
        {
            "run_id": "20260605_010203_abcd",
            "frozen_doc_plan": {"project_id": "proj_old"},
        }
    )

    assert state.frozen_doc_plan is not None
    assert state.frozen_doc_plan.project_id == "proj_old"
    assert state.frozen_doc_plan.missing_information == []


def test_constants_do_not_define_fixed_qdrant_collection_name() -> None:
    assert not hasattr(constants, "QDRANT_COLLECTION_NAME")
    assert "docforge_evidence" not in vars(constants).values()
    assert constants.QDRANT_COLLECTION_PREFIX == "docforge"


def test_draft_version_label_is_restricted() -> None:
    DraftVersion(version_label=DraftVersionLabel.V1)
    DraftVersion(version_label=DraftVersionLabel.V2)
    DraftVersion(version_label=DraftVersionLabel.V3)
    DraftVersion(version_label=DraftVersionLabel.RISK)

    with pytest.raises(ValidationError):
        DraftVersion.model_validate({"version_label": "v4"})


def test_screenshot_binding_status_is_restricted() -> None:
    ScreenshotBinding(status=ScreenshotBindingStatus.BOUND)
    ScreenshotBinding(status=ScreenshotBindingStatus.MISSING)
    ScreenshotBinding(status=ScreenshotBindingStatus.CANDIDATE)
    ScreenshotBinding(status=ScreenshotBindingStatus.REJECTED)

    with pytest.raises(ValidationError):
        ScreenshotBinding.model_validate({"status": "done"})


def test_missing_information_status_is_restricted() -> None:
    MissingInformationItem(question="请补充运行环境", status=MissingInformationStatus.PENDING)
    MissingInformationItem(question="请补充运行环境", status=MissingInformationStatus.ANSWERED)
    MissingInformationItem(question="请补充运行环境", status=MissingInformationStatus.IGNORED)

    with pytest.raises(ValidationError):
        MissingInformationItem.model_validate({"question": "请补充运行环境", "status": "closed"})
