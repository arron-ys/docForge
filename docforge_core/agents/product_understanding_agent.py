"""Evidence-grounded product understanding."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from docforge_core.domain.enums import (
    AllowedUsage,
    CapabilityType,
    CorpusType,
    EvidenceType,
    ImplementationStatus,
    NextAction,
    ProductFactType,
    ValidationStatus,
    WorkflowStatus,
)
from docforge_core.domain.schemas import (
    DocForgeState,
    EvidenceItem,
    EvidenceSupport,
    ProductCapability,
    ProductFact,
    ProductProfile,
)
from docforge_core.evidence.qdrant_store import QdrantStore
from docforge_core.io.run_paths import get_run_dir
from docforge_core.io.state_store import StateStore
from docforge_core.llm.base import LLMMessage, LLMProvider
from docforge_core.llm.prompt_loader import load_prompt
from docforge_core.llm.provider_factory import create_llm_provider

from ._shared import filtered_evidence, transition, unique_strings
from .capability_grounding_verifier import ProductCapabilityGroundingVerifier
from .capability_validation_trace import build_capability_validation_trace
from .profile_entity_grounding_verifier import ProductProfileEntityGroundingVerifier

MISSING_PRODUCT_QUESTION = (
    "当前未发现自有产品资料，无法可靠生成软著产品事实，请上传产品介绍、PRD、HLD 或产品截图。"
)
# These signals only correct implementation status after semantic extraction.
# They never establish that a capability exists or determine its CapabilityType.
PLANNING_STATUS_SIGNALS = (
    "规划",
    "计划",
    "未来",
    "后续",
    "待建设",
    "待实现",
    "拟支持",
    "将支持",
    "暂未上线",
    "尚未上线",
    "未上线",
    "未实现",
    "预计",
    "路线图",
    "建设中",
    "planned",
    "future",
    "roadmap",
    "will support",
)
MIN_CJK_QUOTE_LENGTH = 6
MIN_ASCII_QUOTE_LENGTH = 12

MODULE_BY_CAPABILITY: dict[CapabilityType, str] = {
    CapabilityType.DATA_MANAGEMENT: "数据管理",
    CapabilityType.DATASET_MANAGEMENT: "数据管理",
    CapabilityType.DATA_QUALITY: "数据管理",
    CapabilityType.ANNOTATION: "数据管理",
    CapabilityType.AI_TRAINING: "AI 能力",
    CapabilityType.AI_INFERENCE: "AI 能力",
    CapabilityType.AI_EVALUATION: "AI 能力",
    CapabilityType.MODEL_ASSET_MANAGEMENT: "AI 能力",
    CapabilityType.PERMISSION_MANAGEMENT: "用户与权限管理",
    CapabilityType.USER_MANAGEMENT: "用户与权限管理",
    CapabilityType.WEB_SAAS: "Web 平台功能",
    CapabilityType.SIMULATION_MANAGEMENT: "仿真管理",
    CapabilityType.THREE_D_MODEL_MANAGEMENT: "三维/CAD 模型管理",
    CapabilityType.CAD_MODEL_MANAGEMENT: "三维/CAD 模型管理",
    CapabilityType.FILE_IMPORT_EXPORT: "文件导入导出",
    CapabilityType.SYSTEM_ADMINISTRATION: "系统管理",
}
TECHNICAL_LABEL_BY_CAPABILITY: dict[CapabilityType, str] = {
    CapabilityType.AI_TRAINING: "模型训练",
    CapabilityType.AI_INFERENCE: "模型推理",
    CapabilityType.AI_EVALUATION: "模型评测",
    CapabilityType.MODEL_ASSET_MANAGEMENT: "模型资产管理",
    CapabilityType.THREE_D_MODEL_MANAGEMENT: "三维模型",
    CapabilityType.CAD_MODEL_MANAGEMENT: "CAD 模型",
}


class ProductUnderstandingAgent:
    """Extract semantic capabilities, then validate every claim against evidence."""

    def __init__(
        self,
        state_store: StateStore | None = None,
        qdrant_store: QdrantStore | None = None,
        llm_provider: LLMProvider | None = None,
        grounding_verifier: ProductCapabilityGroundingVerifier | None = None,
        profile_entity_verifier: ProductProfileEntityGroundingVerifier | None = None,
        top_k: int = 10,
    ) -> None:
        self.state_store = state_store or StateStore()
        self.qdrant_store = qdrant_store
        self.llm_provider = llm_provider
        self.grounding_verifier = grounding_verifier
        self.profile_entity_verifier = profile_entity_verifier
        self.top_k = top_k

    def understand_run(self, run_id: str) -> DocForgeState:
        state = self.state_store.load_state(run_id)
        packets = self._build_evidence_packets(state)
        product_fact_evidence = self._product_fact_evidence(state)
        evidence_by_id = {item.evidence_id: item for item in product_fact_evidence}
        evidence_text_by_id = {
            packet["evidence_id"]: f"{packet['summary']}\n{packet['text_excerpt']}"
            for packet in packets
        }

        if not packets:
            state.product_capabilities = []
            state.product_facts = []
            state.product_profile = ProductProfile(product_positioning="待确认")
            if MISSING_PRODUCT_QUESTION not in state.pending_human_questions:
                state.pending_human_questions.append(MISSING_PRODUCT_QUESTION)
        else:
            try:
                llm_data = self._extract_semantic_candidates(packets)
            except (ValueError, TypeError) as exc:
                if "API_KEY" in str(exc):
                    raise
                llm_data = {}
                state.warnings.append(f"ProductUnderstandingAgent 语义抽取失败: {exc}")

            capabilities, rejected = self._validate_capability_candidates(
                llm_data,
                evidence_by_id,
                evidence_text_by_id,
                state.warnings,
            )
            profile_entities = self._validate_profile_entities(
                llm_data,
                evidence_by_id,
                evidence_text_by_id,
                state.warnings,
            )
            state.product_capabilities = capabilities
            state.product_facts = self._facts_from_capabilities(capabilities)
            state.product_profile = self._synthesize_product_profile(
                capabilities,
                llm_data,
                rejected,
                profile_entities,
            )

        transition(
            state,
            WorkflowStatus.REFERENCE_STYLE_ANALYZED,
            WorkflowStatus.PRODUCT_UNDERSTOOD,
            NextAction.DIAGNOSE_SOFTWARE_TYPE,
            "ProductUnderstandingAgent.understand_run",
            "product evidence understood",
        )
        self.state_store.save_state(state)
        return state

    def _build_evidence_packets(self, state: DocForgeState) -> list[dict[str, Any]]:
        evidence = self._product_fact_evidence(state)[: self.top_k]
        run_dir = get_run_dir(state.run_id, self.state_store.data_dir).resolve()
        packets: list[dict[str, Any]] = []
        for item in evidence:
            text_excerpt = self._read_content_excerpt(run_dir, item)
            packets.append(
                {
                    "evidence_id": item.evidence_id,
                    "source_id": item.source_id,
                    "source_type": item.source_type.value,
                    "evidence_type": item.evidence_type.value,
                    "summary": item.summary or "",
                    "text_excerpt": text_excerpt[:2000],
                    "tags": item.tags,
                    "content_ref": item.content_ref,
                    "source_location": item.source_location,
                }
            )
        return packets

    @staticmethod
    def _product_fact_evidence(state: DocForgeState) -> list[EvidenceItem]:
        """Return product evidence that can support text claims, excluding screenshots."""
        return [
            item
            for item in filtered_evidence(
                state,
                CorpusType.PRODUCT_EVIDENCE,
                AllowedUsage.FACTUAL_EVIDENCE,
            )
            if item.evidence_type != EvidenceType.PRODUCT_SCREENSHOT
        ]

    @staticmethod
    def _read_content_excerpt(run_dir: Path, evidence: EvidenceItem) -> str:
        if evidence.content_ref:
            path = (run_dir / evidence.content_ref).resolve()
            try:
                path.relative_to(run_dir)
                if path.is_file():
                    return path.read_text(encoding="utf-8")[:2000]
            except (OSError, UnicodeError, ValueError):
                pass
        return evidence.summary or ""

    def _extract_semantic_candidates(self, packets: list[dict[str, Any]]) -> dict[str, Any]:
        return self._provider().generate_json(
            [
                LLMMessage(role="system", content=load_prompt("product_understanding.md")),
                LLMMessage(
                    role="user",
                    content=json.dumps({"evidence_packets": packets}, ensure_ascii=False, indent=2),
                ),
            ]
        )

    def _validate_capability_candidates(
        self,
        llm_data: dict[str, Any],
        evidence_by_id: dict[str, EvidenceItem],
        evidence_text_by_id: dict[str, str],
        warnings: list[str] | None = None,
    ) -> tuple[list[ProductCapability], list[str]]:
        warnings = warnings if warnings is not None else []
        accepted: list[ProductCapability] = []
        rejected: list[str] = []
        candidates = llm_data.get("capabilities", [])
        if not isinstance(candidates, list):
            return accepted, rejected

        source_grounded: list[tuple[int, dict[str, Any], list[EvidenceSupport]]] = []
        for candidate_index, raw in enumerate(candidates):
            if not isinstance(raw, dict):
                continue
            name = str(raw.get("name", "")).strip()
            if not name:
                warnings.append("ProductUnderstandingAgent 拒绝空名称能力。")
                continue
            supports, reason = self._validated_supports(raw, evidence_by_id, evidence_text_by_id)
            if not supports:
                rejected.append(name)
                warnings.append(f"能力“{name}”证据不足，已拒绝: {reason}")
                continue
            source_grounded.append((candidate_index, raw, supports))

        verifier_candidates = [
            {
                "candidate_index": candidate_index,
                "name": str(raw.get("name", "")),
                "description": str(raw.get("description", "")),
                "capability_type": raw.get("capability_type"),
                "implementation_status": raw.get("implementation_status"),
                "supporting_evidence_ids": raw.get("supporting_evidence_ids", []),
                "supporting_quotes": raw.get("supporting_quotes", []),
            }
            for candidate_index, raw, _supports in source_grounded
        ]
        verifier_results = self._verifier().verify_candidates(
            verifier_candidates,
            evidence_text_by_id,
        )
        verifier_by_index = {
            result["candidate_index"]: result
            for result in verifier_results
            if isinstance(result.get("candidate_index"), int)
        }

        for candidate_index, raw, supports in source_grounded:
            name = str(raw.get("name", "")).strip()
            verifier_result = verifier_by_index.get(candidate_index)
            if verifier_result is None or not verifier_result.get("supported"):
                reason = (
                    str(verifier_result.get("reason"))
                    if verifier_result is not None
                    else "verifier 未返回该 candidate 的结果，已 fail closed。"
                )
                rejected.append(name)
                warnings.append(f"能力“{name}”语义校验未通过，已拒绝: {reason}")
                continue
            if not verifier_result.get("name_supported"):
                rejected.append(name)
                warnings.append(f"能力“{name}”名称不受 quote 支持，已拒绝。")
                continue

            capability_type = self._resolved_capability_type(
                raw,
                verifier_result,
                warnings,
                name,
            )
            if capability_type is None:
                rejected.append(name)
                continue
            implementation_status = self._resolved_implementation_status(
                raw,
                verifier_result,
                warnings,
                name,
            )
            if implementation_status is None:
                rejected.append(name)
                continue
            if implementation_status == ImplementationStatus.CURRENT and any(
                self._has_planning_signal(support.quote) for support in supports
            ):
                implementation_status = ImplementationStatus.PLANNED
                warnings.append(f"能力“{name}”引用规划内容，状态已降级为 planned。")

            confidence = self._clamp_confidence(raw.get("confidence", 0.8))
            capability_id = f"cap_{uuid5(NAMESPACE_URL, self._capability_key(name, raw, capability_type, implementation_status)).hex[:16]}"
            capability = ProductCapability(
                capability_id=capability_id,
                name=name,
                description=str(raw.get("description", "")),
                capability_type=capability_type,
                implementation_status=implementation_status,
                evidence_supports=supports,
                confidence=confidence,
                validation_status=ValidationStatus.VALIDATED,
                reasoning=str(raw.get("reasoning")) if raw.get("reasoning") else None,
            )
            capability.validation_trace = build_capability_validation_trace(
                capability,
                verifier_result,
            )
            accepted.append(capability)
        return accepted, rejected

    @staticmethod
    def _resolved_capability_type(
        raw: dict[str, Any],
        verifier_result: dict[str, Any],
        warnings: list[str],
        name: str,
    ) -> CapabilityType | None:
        if verifier_result.get("capability_type_supported"):
            return ProductUnderstandingAgent._enum_or_default(
                CapabilityType,
                raw.get("capability_type"),
                CapabilityType.OTHER,
                warnings,
                f"能力“{name}”的 capability_type",
            )

        corrected = verifier_result.get("corrected_capability_type")
        try:
            resolved = CapabilityType(str(corrected))
        except (ValueError, TypeError):
            warnings.append(
                f"能力“{name}”的 capability_type 不受支持，"
                "且 verifier 未提供合法修正值，已拒绝。"
            )
            return None
        warnings.append(
            f"能力“{name}”的 capability_type 已由 verifier 修正为 {resolved.value}。"
        )
        return resolved

    @staticmethod
    def _resolved_implementation_status(
        raw: dict[str, Any],
        verifier_result: dict[str, Any],
        warnings: list[str],
        name: str,
    ) -> ImplementationStatus | None:
        if verifier_result.get("implementation_status_supported"):
            return ProductUnderstandingAgent._enum_or_default(
                ImplementationStatus,
                raw.get("implementation_status"),
                ImplementationStatus.UNKNOWN,
                warnings,
                f"能力“{name}”的 implementation_status",
            )

        corrected = verifier_result.get("corrected_implementation_status")
        try:
            resolved = ImplementationStatus(str(corrected))
        except (ValueError, TypeError):
            warnings.append(
                f"能力“{name}”的 implementation_status 不受支持，"
                "且 verifier 未提供合法修正值，已拒绝。"
            )
            return None
        warnings.append(
            f"能力“{name}”的 implementation_status 已由 verifier 修正为 {resolved.value}。"
        )
        return resolved

    def _validated_supports(
        self,
        raw: dict[str, Any],
        evidence_by_id: dict[str, EvidenceItem],
        evidence_text_by_id: dict[str, str],
    ) -> tuple[list[EvidenceSupport], str]:
        evidence_ids = raw.get("supporting_evidence_ids", [])
        quotes = raw.get("supporting_quotes", [])
        if not isinstance(evidence_ids, list) or not evidence_ids:
            return [], "缺少 supporting_evidence_ids"
        if not isinstance(quotes, list) or not quotes:
            return [], "缺少 supporting_quotes"

        valid_evidence: list[EvidenceItem] = []
        for evidence_id in evidence_ids:
            evidence = evidence_by_id.get(str(evidence_id))
            if evidence is None:
                return [], f"evidence_id 不存在或不是 product_evidence: {evidence_id}"
            if (
                evidence.corpus_type != CorpusType.PRODUCT_EVIDENCE
                or evidence.allowed_usage != AllowedUsage.FACTUAL_EVIDENCE
            ):
                return [], f"非法证据来源: {evidence_id}"
            valid_evidence.append(evidence)

        supports: list[EvidenceSupport] = []
        for raw_quote in quotes:
            quote = str(raw_quote).strip()
            matched = next(
                (
                    evidence
                    for evidence in valid_evidence
                    if self._quote_supported(
                        quote,
                        evidence_text_by_id.get(evidence.evidence_id, evidence.summary or ""),
                    )
                ),
                None,
            )
            if matched is None:
                return [], f"quote 无法在引用证据中找到: {quote}"
            supports.append(
                EvidenceSupport(
                    evidence_id=matched.evidence_id,
                    source_id=matched.source_id,
                    quote=quote,
                    confidence=self._clamp_confidence(raw.get("confidence", 0.8)),
                )
            )
        return supports, ""

    def _provider(self) -> LLMProvider:
        if self.llm_provider is None:
            self.llm_provider = create_llm_provider()
        return self.llm_provider

    def _verifier(self) -> ProductCapabilityGroundingVerifier:
        if self.grounding_verifier is None:
            self.grounding_verifier = ProductCapabilityGroundingVerifier(
                llm_provider=self._provider()
            )
        return self.grounding_verifier

    def _profile_entity_verifier(self) -> ProductProfileEntityGroundingVerifier:
        if self.profile_entity_verifier is None:
            self.profile_entity_verifier = ProductProfileEntityGroundingVerifier(
                llm_provider=self._provider()
            )
        return self.profile_entity_verifier

    @staticmethod
    def _quote_supported(quote: str, evidence_text: str) -> bool:
        normalized_quote = ProductUnderstandingAgent._normalize_text(quote)
        normalized_evidence = ProductUnderstandingAgent._normalize_text(evidence_text)
        if not normalized_quote:
            return False
        ascii_only = normalized_quote.isascii()
        minimum = MIN_ASCII_QUOTE_LENGTH if ascii_only else MIN_CJK_QUOTE_LENGTH
        return len(normalized_quote) >= minimum and normalized_quote in normalized_evidence

    def _synthesize_product_profile(
        self,
        capabilities: list[ProductCapability],
        llm_data: dict[str, Any],
        rejected: list[str],
        profile_entities: dict[str, Any],
    ) -> ProductProfile:
        current = [
            item
            for item in capabilities
            if item.validation_status == ValidationStatus.VALIDATED
            and item.implementation_status == ImplementationStatus.CURRENT
        ]
        uncertain = [
            item.name
            for item in capabilities
            if item.implementation_status in {ImplementationStatus.PLANNED, ImplementationStatus.UNKNOWN}
        ]
        uncertain.extend(f"证据不足：{name}" for name in rejected)
        uncertain.extend(self._uncertain_item_names(llm_data.get("uncertain_items")))

        uncertain.extend(
            f"证据不足：{name}" for name in profile_entities["rejected_entities"]
        )
        uncertain.extend(
            f"规划中：{name}" for name in profile_entities["planned_entities"]
        )
        uncertain.extend(
            f"状态待确认：{name}" for name in profile_entities["unknown_entities"]
        )

        types = {item.capability_type for item in current}
        modules = unique_strings([MODULE_BY_CAPABILITY[item] for item in types if item in MODULE_BY_CAPABILITY])
        technical = unique_strings(
            [TECHNICAL_LABEL_BY_CAPABILITY[item] for item in types if item in TECHNICAL_LABEL_BY_CAPABILITY]
        )
        positioning = self._positioning_from_types(types)
        industry = ["汽车工业软件"] if CapabilityType.AUTOMOTIVE_DOMAIN in types else []
        return ProductProfile(
            product_positioning=positioning,
            target_users=profile_entities["target_users"],
            core_modules=modules,
            core_workflows=profile_entities["workflows"],
            business_objects=profile_entities["business_objects"],
            page_list=profile_entities["pages"],
            feature_list=[item.name for item in current],
            technical_keywords=technical,
            industry_keywords=industry,
            uncertain_features=unique_strings(uncertain),
        )

    def _validate_profile_entities(
        self,
        llm_data: dict[str, Any],
        evidence_by_id: dict[str, EvidenceItem],
        evidence_text_by_id: dict[str, str],
        warnings: list[str],
    ) -> dict[str, Any]:
        field_types = (
            ("business_objects", "business_object"),
            ("target_users", "target_user"),
            ("pages", "page"),
            ("workflows", "workflow"),
        )
        source_grounded: list[
            tuple[int, str, str, dict[str, Any], list[EvidenceSupport]]
        ] = []
        rejected: list[str] = []
        entity_index = 0

        for field_name, entity_type in field_types:
            raw_items = llm_data.get(field_name, [])
            if not isinstance(raw_items, list):
                continue
            for raw in raw_items:
                if not isinstance(raw, dict):
                    continue
                name = str(raw.get("name", "")).strip()
                if not name:
                    warnings.append(f"{entity_type} 拒绝空名称 entity。")
                    entity_index += 1
                    continue
                supports, reason = self._validated_supports(
                    raw,
                    evidence_by_id,
                    evidence_text_by_id,
                )
                if not supports:
                    rejected.append(name)
                    warnings.append(f"{entity_type}“{name}”证据不足，已拒绝: {reason}")
                else:
                    source_grounded.append(
                        (entity_index, field_name, entity_type, raw, supports)
                    )
                entity_index += 1

        verifier_entities = [
            {
                "entity_index": index,
                "entity_type": entity_type,
                "name": str(raw.get("name", "")),
                "description": raw.get("description"),
                "steps": raw.get("steps"),
                "implementation_status": raw.get(
                    "implementation_status",
                    ImplementationStatus.UNKNOWN.value,
                ),
                "supporting_evidence_ids": raw.get("supporting_evidence_ids", []),
                "supporting_quotes": raw.get("supporting_quotes", []),
            }
            for index, _field_name, entity_type, raw, _supports in source_grounded
        ]
        verifier_results = self._profile_entity_verifier().verify_entities(
            verifier_entities,
            evidence_text_by_id,
        )
        verifier_by_index = {
            result["entity_index"]: result
            for result in verifier_results
            if isinstance(result.get("entity_index"), int)
        }
        accepted: dict[str, list[Any]] = {
            "business_objects": [],
            "target_users": [],
            "pages": [],
            "workflows": [],
        }
        planned: list[str] = []
        unknown: list[str] = []

        for index, field_name, entity_type, raw, supports in source_grounded:
            name = str(raw.get("name", "")).strip()
            result = verifier_by_index.get(index)
            if (
                result is None
                or not result.get("supported")
                or not result.get("name_supported")
                or not result.get("entity_type_supported")
            ):
                reason = (
                    str(result.get("reason"))
                    if result is not None
                    else "profile entity verifier 未返回该 entity 的结果，已 fail closed。"
                )
                rejected.append(name)
                warnings.append(f"{entity_type}“{name}”语义校验未通过，已拒绝: {reason}")
                continue

            implementation_status = self._resolved_profile_entity_status(
                raw,
                result,
                warnings,
                entity_type,
                name,
            )
            if implementation_status is None:
                rejected.append(name)
                continue
            if implementation_status == ImplementationStatus.CURRENT and any(
                self._has_planning_signal(support.quote) for support in supports
            ):
                implementation_status = ImplementationStatus.PLANNED
                warnings.append(
                    f"{entity_type}“{name}”引用规划内容，状态已降级为 planned。"
                )
            if implementation_status == ImplementationStatus.PLANNED:
                planned.append(name)
                continue
            if implementation_status == ImplementationStatus.UNKNOWN:
                unknown.append(name)
                continue

            if field_name == "workflows":
                accepted[field_name].append(
                    {
                        "name": name,
                        "steps": raw.get("steps", []),
                        "supporting_evidence_ids": unique_strings(
                            [support.evidence_id for support in supports]
                        ),
                    }
                )
            else:
                accepted[field_name].append(name)

        return {
            "business_objects": unique_strings(accepted["business_objects"]),
            "target_users": unique_strings(accepted["target_users"]),
            "pages": unique_strings(accepted["pages"]),
            "workflows": accepted["workflows"],
            "rejected_entities": unique_strings(rejected),
            "planned_entities": unique_strings(planned),
            "unknown_entities": unique_strings(unknown),
            "non_current_entities": unique_strings([*planned, *unknown]),
        }

    @staticmethod
    def _resolved_profile_entity_status(
        raw: dict[str, Any],
        verifier_result: dict[str, Any],
        warnings: list[str],
        entity_type: str,
        name: str,
    ) -> ImplementationStatus | None:
        if verifier_result.get("implementation_status_supported"):
            return ProductUnderstandingAgent._enum_or_default(
                ImplementationStatus,
                raw.get("implementation_status", ImplementationStatus.UNKNOWN.value),
                ImplementationStatus.UNKNOWN,
                warnings,
                f"{entity_type}“{name}”的 implementation_status",
            )

        corrected = verifier_result.get("corrected_implementation_status")
        try:
            resolved = ImplementationStatus(str(corrected))
        except (ValueError, TypeError):
            warnings.append(
                f"{entity_type}“{name}”的 implementation_status 不受支持，"
                "且 verifier 未提供合法修正值，已拒绝。"
            )
            return None
        warnings.append(
            f"{entity_type}“{name}”的 implementation_status 已由 verifier 修正为 "
            f"{resolved.value}。"
        )
        return resolved

    @staticmethod
    def _facts_from_capabilities(capabilities: list[ProductCapability]) -> list[ProductFact]:
        return [
            ProductFact(
                fact_id=f"fact_{item.capability_id}",
                fact_type=ProductUnderstandingAgent._fact_type(item.capability_type),
                content=item.name,
                source_ids=unique_strings([support.source_id for support in item.evidence_supports]),
                confidence=item.confidence,
                is_confirmed=False,
                implementation_status=item.implementation_status,
                capability_type=item.capability_type,
                supporting_evidence_ids=unique_strings(
                    [support.evidence_id for support in item.evidence_supports]
                ),
                supporting_quotes=[support.quote for support in item.evidence_supports],
                reasoning=item.reasoning,
                validation_status=item.validation_status,
            )
            for item in capabilities
            if item.validation_status == ValidationStatus.VALIDATED
        ]

    @staticmethod
    def _fact_type(capability_type: CapabilityType) -> ProductFactType:
        if capability_type in {CapabilityType.PERMISSION_MANAGEMENT, CapabilityType.USER_MANAGEMENT}:
            return ProductFactType.PERMISSION
        if capability_type in {
            CapabilityType.DATA_MANAGEMENT,
            CapabilityType.DATASET_MANAGEMENT,
            CapabilityType.DATA_QUALITY,
            CapabilityType.ANNOTATION,
        }:
            return ProductFactType.DATA_OBJECT
        if capability_type == CapabilityType.WEB_SAAS:
            return ProductFactType.PAGE
        return ProductFactType.FEATURE

    @staticmethod
    def _positioning_from_types(types: set[CapabilityType]) -> str:
        labels: list[str] = []
        if CapabilityType.WEB_SAAS in types:
            labels.append("Web/SaaS 平台")
        if types.intersection(
            {
                CapabilityType.DATA_MANAGEMENT,
                CapabilityType.DATASET_MANAGEMENT,
                CapabilityType.DATA_QUALITY,
                CapabilityType.ANNOTATION,
            }
        ):
            labels.append("数据管理相关系统")
        if types.intersection(
            {
                CapabilityType.AI_TRAINING,
                CapabilityType.AI_INFERENCE,
                CapabilityType.AI_EVALUATION,
                CapabilityType.MODEL_ASSET_MANAGEMENT,
            }
        ):
            labels.append("AI 平台相关系统")
        if types.intersection(
            {
                CapabilityType.SIMULATION_MANAGEMENT,
                CapabilityType.THREE_D_MODEL_MANAGEMENT,
                CapabilityType.CAD_MODEL_MANAGEMENT,
            }
        ):
            labels.append("工业软件相关系统")
        return "、".join(labels) or "待确认"

    @staticmethod
    def _uncertain_item_names(raw_items: Any) -> list[str]:
        if not isinstance(raw_items, list):
            return []
        return [
            str(item.get("name") or item.get("reason"))
            for item in raw_items
            if isinstance(item, dict) and (item.get("name") or item.get("reason"))
        ]

    @staticmethod
    def _enum_or_default(
        enum_type: type[Any],
        raw_value: Any,
        default: Any,
        warnings: list[str],
        label: str,
    ) -> Any:
        try:
            return enum_type(raw_value)
        except (ValueError, TypeError):
            warnings.append(f"{label} 无效，已使用 {default.value}。")
            return default

    @staticmethod
    def _clamp_confidence(value: Any) -> float:
        try:
            return max(0.0, min(float(value), 1.0))
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _normalize_text(text: str) -> str:
        return re.sub(r"\s+", "", text).lower()

    @staticmethod
    def _has_planning_signal(text: str) -> bool:
        normalized = text.lower()
        return any(signal.lower() in normalized for signal in PLANNING_STATUS_SIGNALS)

    @staticmethod
    def _capability_key(
        name: str,
        raw: dict[str, Any],
        capability_type: CapabilityType,
        implementation_status: ImplementationStatus,
    ) -> str:
        return "|".join(
            [
                name,
                capability_type.value,
                implementation_status.value,
                ",".join(map(str, raw.get("supporting_evidence_ids", []))),
            ]
        )
