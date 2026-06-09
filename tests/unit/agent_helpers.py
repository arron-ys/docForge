from pathlib import Path
from typing import Any

from docforge_core.agents.capability_validation_trace import (
    build_capability_validation_trace,
)
from docforge_core.domain.enums import (
    AllowedUsage,
    CapabilityType,
    CorpusType,
    EvidenceStrength,
    EvidenceType,
    FileType,
    ImplementationStatus,
    SourceType,
    ValidationStatus,
    WorkflowStatus,
)
from docforge_core.domain.schemas import (
    DocForgeState,
    EvidenceItem,
    EvidenceSupport,
    ProductCapability,
)
from docforge_core.io.state_store import StateStore


def product_evidence(
    evidence_id: str = "ev_product",
    source_id: str = "product_source",
    summary: str = "数据集导入页面支持权限管理，当前版本明确支持该产品能力",
    tags: list[str] | None = None,
    evidence_type: EvidenceType = EvidenceType.PRODUCT_DOCUMENT,
) -> EvidenceItem:
    source_type = SourceType.SCREENSHOT if evidence_type == EvidenceType.PRODUCT_SCREENSHOT else SourceType.PRD
    is_screenshot = evidence_type == EvidenceType.PRODUCT_SCREENSHOT
    return EvidenceItem(
        evidence_id=evidence_id,
        source_id=source_id,
        source_type=source_type,
        file_type=FileType.PNG if source_type == SourceType.SCREENSHOT else FileType.TXT,
        evidence_type=evidence_type,
        corpus_type=CorpusType.PRODUCT_EVIDENCE,
        allowed_usage=(
            AllowedUsage.DISPLAY_MATERIAL_ONLY
            if is_screenshot
            else AllowedUsage.FACTUAL_EVIDENCE
        ),
        evidence_strength=(
            EvidenceStrength.NOT_ALLOWED_AS_FACT if is_screenshot else EvidenceStrength.MEDIUM
        ),
        summary=summary,
        tags=tags or [],
        confidence=0.8,
    )


def reference_evidence(
    evidence_id: str = "ev_reference",
    source_id: str = "reference_source",
    summary: str = "参考产品包含秘密模块，章节采用操作手册写法",
) -> EvidenceItem:
    return EvidenceItem(
        evidence_id=evidence_id,
        source_id=source_id,
        source_type=SourceType.REFERENCE_SOFT_COPYRIGHT_DOC,
        file_type=FileType.TXT,
        evidence_type=EvidenceType.REFERENCE_STYLE_ONLY,
        corpus_type=CorpusType.REFERENCE_STYLE,
        allowed_usage=AllowedUsage.STYLE_ONLY,
        evidence_strength=EvidenceStrength.NOT_ALLOWED_AS_FACT,
        summary=summary,
        tags=["reference_style"],
    )


def save_state(
    tmp_path: Path,
    status: WorkflowStatus,
    evidence: list[EvidenceItem] | None = None,
) -> tuple[StateStore, DocForgeState]:
    store = StateStore(data_dir=tmp_path)
    state = store.create_initial_state()
    state.workflow_status = status
    state.evidence_map = evidence or []
    store.save_state(state)
    return store, state


def capability(
    capability_id: str,
    capability_type: CapabilityType,
    implementation_status: ImplementationStatus = ImplementationStatus.CURRENT,
    validation_status: ValidationStatus = ValidationStatus.VALIDATED,
    name: str = "能力",
) -> ProductCapability:
    supports = (
        [EvidenceSupport(evidence_id="ev_product", source_id="product_source", quote="当前版本明确支持该产品能力")]
        if validation_status == ValidationStatus.VALIDATED
        else []
    )
    result = ProductCapability(
        capability_id=capability_id,
        name=name,
        capability_type=capability_type,
        implementation_status=implementation_status,
        evidence_supports=supports,
        confidence=0.9,
        validation_status=validation_status,
    )
    if validation_status == ValidationStatus.VALIDATED:
        result.validation_trace = build_capability_validation_trace(
            result,
            {
                "supported": True,
                "name_supported": True,
                "capability_type_supported": True,
                "implementation_status_supported": True,
                "reason": "测试 helper 构造的合法语义校验凭证",
            },
        )
    return result


def accepting_verifier_response(llm_data: dict[str, Any]) -> dict[str, Any]:
    raw_capabilities = llm_data.get("capabilities", [])
    capabilities = raw_capabilities if isinstance(raw_capabilities, list) else []
    return {
        "results": [
            {
                "candidate_index": index,
                "supported": True,
                "name_supported": True,
                "capability_type_supported": True,
                "implementation_status_supported": True,
                "corrected_capability_type": None,
                "corrected_implementation_status": None,
                "reason": "quote 语义支持 candidate",
            }
            for index, candidate in enumerate(capabilities)
            if isinstance(candidate, dict)
        ]
    }


def accepting_profile_entity_response(llm_data: dict[str, Any]) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    entity_index = 0
    for field_name, entity_type in (
        ("business_objects", "business_object"),
        ("target_users", "target_user"),
        ("pages", "page"),
        ("workflows", "workflow"),
    ):
        raw_entities = llm_data.get(field_name, [])
        entities = raw_entities if isinstance(raw_entities, list) else []
        for entity in entities:
            if isinstance(entity, dict):
                results.append(
                    {
                        "entity_index": entity_index,
                        "supported": True,
                        "name_supported": True,
                        "entity_type_supported": True,
                        "implementation_status_supported": True,
                        "corrected_implementation_status": None,
                        "reason": f"quote 语义支持 {entity_type}",
                    }
                )
                entity_index += 1
    return {"results": results}
