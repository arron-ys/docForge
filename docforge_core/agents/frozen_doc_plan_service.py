"""Freeze a human-confirmed document generation contract."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from docforge_core.domain.enums import (
    AllowedUsage,
    ConfirmationStatus,
    ConfirmationType,
    CorpusType,
    EvidenceType,
    ImplementationStatus,
    LockedBy,
    LockedStatus,
    NextAction,
    ValidationStatus,
    WorkflowStatus,
)
from docforge_core.domain.schemas import (
    DocForgeState,
    EvidenceItem,
    FrozenDocPlan,
    HumanConfirmation,
    ProductCapability,
    ProductFact,
    TemplateConfirmationDecision,
)
from docforge_core.io.run_paths import get_run_dir
from docforge_core.io.state_store import StateStore

from ._shared import transition, unique_strings
from .capability_validation_trace import validate_capability_trace
from .confirmation_decision_validator import validate_template_confirmation_decision
from .human_confirm_gate import CONFIRMATION_SOURCE_KEY, DECISION_METADATA_KEY
from .title_safety import is_forbidden_title

QUOTE_TEXT_PATTERN = re.compile(r"[^0-9a-z\u4e00-\u9fff]+")
CHINESE_TEXT_PATTERN = re.compile(r"[\u4e00-\u9fff]")
MAX_QUOTE_CONTENT_BYTES = 1_000_000


def _normalize_quote_text(text: str) -> str:
    """Keep only Chinese, English, and digits for exact quote containment."""
    return QUOTE_TEXT_PATTERN.sub("", text.lower())


def _quote_exists_in_evidence(quote: str, evidence_text: str) -> bool:
    """Require a sufficiently specific quote to appear fully in evidence text."""
    normalized_quote = _normalize_quote_text(quote)
    if not normalized_quote:
        return False
    minimum_length = 6 if CHINESE_TEXT_PATTERN.search(normalized_quote) else 12
    if len(normalized_quote) < minimum_length:
        return False
    return normalized_quote in _normalize_quote_text(evidence_text)


class FrozenDocPlanService:
    """Create FrozenDocPlan only from confirmed, evidence-grounded state."""

    def __init__(self, state_store: StateStore | None = None) -> None:
        self.state_store = state_store or StateStore()

    def freeze_confirmed_plan(self, run_id: str) -> DocForgeState:
        state = self.state_store.load_state(run_id)
        if state.workflow_status != WorkflowStatus.USER_CONFIRMED:
            raise ValueError("冻结文档计划要求 workflow_status 为 USER_CONFIRMED")
        if state.template_strategy is None:
            raise ValueError("冻结文档计划要求存在 template_strategy")
        if state.diagnosis_result is None:
            raise ValueError("冻结文档计划要求存在 diagnosis_result")

        confirmation = self._confirmed_template_confirmation(state)
        if confirmation is None:
            raise ValueError("不存在已确认的 template_strategy HumanConfirmation")
        raw_decision = confirmation.metadata.get(DECISION_METADATA_KEY)
        if not isinstance(raw_decision, dict):
            raise ValueError("无法从 HumanConfirmation 恢复 template confirmation decision")
        decision = TemplateConfirmationDecision.model_validate(raw_decision)
        validate_template_confirmation_decision(decision, state.template_strategy)
        from docforge_core.workflow.run_settings import get_run_settings

        run_settings = get_run_settings(state)

        current_candidates = [
            item
            for item in state.product_capabilities
            if item.validation_status == ValidationStatus.VALIDATED
            and item.implementation_status == ImplementationStatus.CURRENT
        ]
        current = self._validate_current_capabilities(state, current_candidates)
        planned = [
            item
            for item in state.product_capabilities
            if item.implementation_status == ImplementationStatus.PLANNED
        ]
        unknown = [
            item
            for item in state.product_capabilities
            if item.implementation_status == ImplementationStatus.UNKNOWN
        ]
        allowed_current = unique_strings([item.name for item in current])
        forbidden_current = unique_strings(
            [
                *[item.name for item in planned],
                *[item.name for item in unknown],
                *state.product_profile.uncertain_features,
            ]
        )
        if any(
            is_forbidden_title(feature_name, forbidden_current)
            for feature_name in allowed_current
        ):
            raise ValueError(
                "allowed_current_feature_names 不得包含 planned / unknown / 证据不足功能"
            )
        if any(
            is_forbidden_title(chapter, forbidden_current)
            for chapter in decision.selected_top_level_chapters
        ):
            raise ValueError("一级目录不得包含 planned / unknown / 证据不足功能或其变体")

        evidence_trace = self._build_evidence_trace(current)
        current_facts = self._validate_current_facts(state, current)

        missing_information: list[dict[str, Any]] = []
        risk_notes = list(state.diagnosis_result.risk_notes)
        if not state.target_product_name.strip():
            missing_information.append(
                {
                    "field": "target_product_name",
                    "question": "请补充软件名称。",
                    "reason": "FrozenDocPlan 不得伪造软件名称。",
                }
            )
            risk_notes.append("软件名称待补充")

        now = datetime.now(UTC).isoformat()
        state.frozen_doc_plan = FrozenDocPlan(
            project_id=state.project_id,
            locked_status=LockedStatus.LOCKED,
            locked_at=now,
            locked_by=(
                LockedBy.ORCHESTRATOR
                if confirmation.metadata.get(CONFIRMATION_SOURCE_KEY) == "auto"
                else LockedBy.HUMAN
            ),
            software_identity={
                "project_id": state.project_id,
                "project_name": state.project_name,
                "target_doc_type": state.target_doc_type,
                "selected_doc_output_type": run_settings["doc_output_type"],
                "reference_style_strength": run_settings["reference_style_strength"],
                "target_product_name": state.target_product_name,
                "version": self._software_version(state),
                "software_version": self._software_version(state),
                "user_goal": state.user_goal,
                "output_format": state.output_requirements.get("output_format", "docx"),
            },
            diagnosis_snapshot=state.diagnosis_result.model_dump(mode="json"),
            template_decision={
                "base_template_id": decision.selected_base_template_id,
                "base_template_name": decision.selected_base_template_name,
                "selected_enhancement_pack_ids": decision.selected_enhancement_pack_ids,
                "selected_top_level_chapters": decision.selected_top_level_chapters,
                "selected_optional_chapters": decision.selected_optional_chapters,
                "acknowledged_risk_chapters": decision.acknowledged_risk_chapters,
                "excluded_chapters": decision.excluded_chapters,
                "accepted_recommendation": decision.accepted_recommendation,
                "user_notes": decision.user_notes,
                "risk_acknowledged": decision.risk_acknowledged,
            },
            chapter_policy={
                "locked_top_level_chapters": decision.selected_top_level_chapters,
                "optional_chapters": decision.selected_optional_chapters,
                "risk_chapters": state.template_strategy.risk_chapters,
                "excluded_chapters": decision.excluded_chapters,
                "can_outline_add_level_2_sections": True,
                "can_outline_change_level_1_sections": False,
                "requires_reconfirmation_to_change_level_1": True,
            },
            feature_policy={
                "current_capabilities": self._dump_safe_capabilities(current),
                "planned_capabilities": self._dump_safe_capabilities(planned),
                "unknown_capabilities": self._dump_safe_capabilities(unknown),
                "current_facts": self._dump_safe_facts(current_facts),
                "unsupported_or_rejected_features": state.product_profile.uncertain_features,
                "allowed_current_feature_names": allowed_current,
                "forbidden_as_current_feature_names": forbidden_current,
            },
            evidence_policy=self._evidence_policy(state, evidence_trace),
            screenshot_policy=self._screenshot_policy(state),
            writing_policy=self._writing_policy(state),
            quality_gate_policy=self._quality_gate_policy(state),
            downstream_permissions={
                "outline_agent_can_create_subsections": True,
                "outline_agent_can_change_top_level_chapters": False,
                "writer_agent_can_use_product_evidence_only": True,
                "writer_agent_can_use_reference_style_as_fact": False,
                "audit_agent_must_check_reference_contamination": True,
                "audit_agent_must_check_future_as_current": True,
                "changing_top_level_chapters_requires_human_reconfirmation": True,
            },
            missing_information=missing_information,
            risk_notes=unique_strings(risk_notes),
        )
        transition(
            state,
            WorkflowStatus.USER_CONFIRMED,
            WorkflowStatus.PLAN_FROZEN,
            NextAction.CREATE_OUTLINE,
            "FrozenDocPlanService.freeze_confirmed_plan",
            "confirmed document plan frozen",
        )
        self.state_store.save_state(state)
        return state

    @staticmethod
    def _confirmed_template_confirmation(state: DocForgeState) -> HumanConfirmation | None:
        return next(
            (
                item
                for item in reversed(state.human_confirmations)
                if item.confirmation_type == ConfirmationType.TEMPLATE_STRATEGY
                and item.status == ConfirmationStatus.CONFIRMED
            ),
            None,
        )

    @staticmethod
    def _software_version(state: DocForgeState) -> str:
        return str(
            state.output_requirements.get("version")
            or state.output_requirements.get("software_version")
            or ""
        ).strip()

    def _validate_current_capabilities(
        self,
        state: DocForgeState,
        current: list[ProductCapability],
    ) -> list[ProductCapability]:
        evidence_by_id = {item.evidence_id: item for item in state.evidence_map}
        reference_source_ids = set(state.reference_source_ids).union(
            item.source_id
            for item in state.evidence_map
            if item.corpus_type == CorpusType.REFERENCE_STYLE
            or item.allowed_usage == AllowedUsage.STYLE_ONLY
        )
        for capability in current:
            validate_capability_trace(capability)
            if (
                capability.validation_status != ValidationStatus.VALIDATED
                or capability.implementation_status != ImplementationStatus.CURRENT
            ):
                raise ValueError("current capability 必须为 validated / current")
            if not capability.evidence_supports:
                raise ValueError(f"current capability {capability.capability_id} 缺少 evidence_supports")
            for support in capability.evidence_supports:
                if not support.source_id.strip():
                    raise ValueError("current capability evidence_support source_id 不得为空")
                if not support.quote.strip():
                    raise ValueError("current capability evidence_support quote 不得为空")
                evidence = evidence_by_id.get(support.evidence_id)
                if evidence is None:
                    raise ValueError(f"current capability 引用不存在的 evidence: {support.evidence_id}")
                if evidence.evidence_type == EvidenceType.PRODUCT_SCREENSHOT:
                    raise ValueError(
                        "current capability 不得引用截图 evidence 作为产品事实依据"
                    )
                if (
                    evidence.corpus_type != CorpusType.PRODUCT_EVIDENCE
                    or evidence.allowed_usage != AllowedUsage.FACTUAL_EVIDENCE
                ):
                    raise ValueError("current capability 只能引用 product_evidence / factual_evidence")
                if support.source_id != evidence.source_id:
                    raise ValueError(
                        "current capability evidence_support source_id "
                        "必须与 evidence.source_id 一致"
                    )
                if support.source_id in reference_source_ids:
                    raise ValueError(
                        "current capability evidence_support source_id 不得引用 reference source"
                    )
                evidence_text = self._evidence_text_for_quote_check(state, evidence)
                if not _quote_exists_in_evidence(support.quote, evidence_text):
                    raise ValueError(
                        "current capability EvidenceSupport quote 不存在于对应 evidence 文本中"
                    )
        return current

    @staticmethod
    def _build_evidence_trace(
        current: list[ProductCapability],
    ) -> list[dict[str, Any]]:
        trace: list[dict[str, Any]] = []
        for capability in current:
            for support in capability.evidence_supports:
                trace.append(
                    {
                        "capability_id": capability.capability_id,
                        "capability_name": capability.name,
                        "evidence_id": support.evidence_id,
                        "source_id": support.source_id,
                        "quote": support.quote,
                        "corpus_type": CorpusType.PRODUCT_EVIDENCE.value,
                        "allowed_usage": AllowedUsage.FACTUAL_EVIDENCE.value,
                    }
                )
        return trace

    @staticmethod
    def _dump_safe_capabilities(
        capabilities: list[ProductCapability],
    ) -> list[dict[str, Any]]:
        return [
            {
                "capability_id": item.capability_id,
                "name": item.name,
                "capability_type": item.capability_type.value,
                "implementation_status": item.implementation_status.value,
                "validation_status": item.validation_status.value,
                "confidence": item.confidence,
                "validation_trace": (
                    {
                        "validator_name": item.validation_trace.validator_name,
                        "source_grounded": item.validation_trace.source_grounded,
                        "semantic_grounded": item.validation_trace.semantic_grounded,
                        "claim_hash": item.validation_trace.claim_hash,
                        "evidence_supports_hash": (
                            item.validation_trace.evidence_supports_hash
                        ),
                    }
                    if item.validation_trace is not None
                    else None
                ),
                "evidence_supports": [
                    {
                        "evidence_id": support.evidence_id,
                        "source_id": support.source_id,
                        "quote": support.quote,
                        "confidence": support.confidence,
                    }
                    for support in item.evidence_supports
                ],
            }
            for item in capabilities
        ]

    def _validate_current_facts(
        self,
        state: DocForgeState,
        current: list[ProductCapability],
    ) -> list[ProductFact]:
        evidence_by_id = {item.evidence_id: item for item in state.evidence_map}
        evidence_by_source_id: dict[str, list[EvidenceItem]] = {}
        for evidence_item in state.evidence_map:
            evidence_by_source_id.setdefault(evidence_item.source_id, []).append(
                evidence_item
            )

        current_facts = [
            item
            for item in state.product_facts
            if item.validation_status == ValidationStatus.VALIDATED
            and item.implementation_status == ImplementationStatus.CURRENT
        ]
        capabilities_by_fact_id = {
            f"fact_{item.capability_id}": item for item in current
        }
        for fact in current_facts:
            if not fact.supporting_evidence_ids:
                raise ValueError(
                    f"current ProductFact {fact.fact_id} 缺少 supporting_evidence_ids"
                )
            for evidence_id in fact.supporting_evidence_ids:
                supporting_evidence = evidence_by_id.get(evidence_id)
                if supporting_evidence is None:
                    raise ValueError(
                        f"current ProductFact 引用不存在的 evidence: {evidence_id}"
                    )
                if supporting_evidence.evidence_type == EvidenceType.PRODUCT_SCREENSHOT:
                    raise ValueError(
                        "current ProductFact 不得引用截图 evidence 作为产品事实依据"
                    )
                if (
                    supporting_evidence.corpus_type != CorpusType.PRODUCT_EVIDENCE
                    or supporting_evidence.allowed_usage != AllowedUsage.FACTUAL_EVIDENCE
                ):
                    raise ValueError(
                        "current ProductFact 只能引用 product_evidence / factual_evidence，"
                        "不得引用 reference_style"
                    )
            for source_id in fact.source_ids:
                source_evidence = evidence_by_source_id.get(source_id)
                if not source_evidence:
                    raise ValueError(
                        f"current ProductFact source_id 无法追溯到 evidence_map: {source_id}"
                    )
                if any(
                    item.corpus_type != CorpusType.PRODUCT_EVIDENCE
                    or item.allowed_usage != AllowedUsage.FACTUAL_EVIDENCE
                    or item.evidence_type == EvidenceType.PRODUCT_SCREENSHOT
                    for item in source_evidence
                ):
                    raise ValueError(
                        "current ProductFact source_ids 不得引用 reference_style source_id "
                        "或截图 source_id"
                    )
            capability = capabilities_by_fact_id.get(fact.fact_id)
            if capability is None:
                raise ValueError(
                    "current ProductFact 必须绑定到 validated + current ProductCapability"
                )
            if fact.content != capability.name:
                raise ValueError("current ProductFact content 必须等于绑定 capability.name")
            if fact.capability_type != capability.capability_type:
                raise ValueError(
                    "current ProductFact capability_type 必须等于绑定 capability.capability_type"
                )
            if (
                fact.implementation_status != capability.implementation_status
                or fact.validation_status != capability.validation_status
            ):
                raise ValueError("current ProductFact 状态必须与绑定 capability 一致")

            capability_evidence_ids = {
                support.evidence_id for support in capability.evidence_supports
            }
            capability_source_ids = {
                support.source_id for support in capability.evidence_supports
            }
            capability_quotes = {support.quote for support in capability.evidence_supports}
            if not set(fact.supporting_evidence_ids).issubset(capability_evidence_ids):
                raise ValueError(
                    "current ProductFact supporting_evidence_ids 必须来自绑定 capability"
                )
            if not set(fact.source_ids).issubset(capability_source_ids):
                raise ValueError("current ProductFact source_ids 必须来自绑定 capability")
            if not set(fact.supporting_quotes).issubset(capability_quotes):
                raise ValueError(
                    "current ProductFact supporting_quotes 必须来自绑定 capability"
                )
            for quote in fact.supporting_quotes:
                matching_supports = [
                    support
                    for support in capability.evidence_supports
                    if support.quote == quote
                ]
                if not any(
                    _quote_exists_in_evidence(
                        quote,
                        self._evidence_text_for_quote_check(
                            state,
                            evidence_by_id[support.evidence_id],
                        ),
                    )
                    for support in matching_supports
                ):
                    raise ValueError(
                        "current ProductFact supporting quote 不存在于对应 evidence 文本中"
                    )
        return current_facts

    @staticmethod
    def _dump_safe_facts(facts: list[ProductFact]) -> list[dict[str, Any]]:
        return [
            {
                "fact_id": item.fact_id,
                "fact_type": item.fact_type.value,
                "content": item.content,
                "source_ids": item.source_ids,
                "confidence": item.confidence,
                "implementation_status": item.implementation_status.value,
                "capability_type": (
                    item.capability_type.value if item.capability_type is not None else None
                ),
                "supporting_evidence_ids": item.supporting_evidence_ids,
                "supporting_quotes": item.supporting_quotes,
                "validation_status": item.validation_status.value,
            }
            for item in facts
        ]

    def _evidence_text_for_quote_check(
        self,
        state: DocForgeState,
        evidence: EvidenceItem,
    ) -> str:
        parts = [evidence.summary or "", evidence.notes or ""]
        parts.extend(self._string_values(evidence.extracted_facts))

        if evidence.content_ref and evidence.evidence_type != EvidenceType.PRODUCT_SCREENSHOT:
            content_ref = Path(evidence.content_ref)
            if not content_ref.is_absolute():
                run_dir = get_run_dir(state.run_id, self.state_store.data_dir).resolve()
                content_path = (run_dir / content_ref).resolve()
                try:
                    content_path.relative_to(run_dir)
                    if (
                        content_path.is_file()
                        and content_path.stat().st_size <= MAX_QUOTE_CONTENT_BYTES
                    ):
                        parts.append(content_path.read_text(encoding="utf-8"))
                except (OSError, UnicodeError, ValueError):
                    pass
        return "\n".join(part for part in parts if part)

    @staticmethod
    def _string_values(value: Any) -> list[str]:
        if isinstance(value, str):
            return [value]
        if isinstance(value, dict):
            return [
                text
                for nested in value.values()
                for text in FrozenDocPlanService._string_values(nested)
            ]
        if isinstance(value, list):
            return [
                text
                for nested in value
                for text in FrozenDocPlanService._string_values(nested)
            ]
        return []

    @staticmethod
    def _evidence_policy(
        state: DocForgeState,
        evidence_trace: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return {
            "factual_evidence_filter": {
                "corpus_type": CorpusType.PRODUCT_EVIDENCE.value,
                "allowed_usage": AllowedUsage.FACTUAL_EVIDENCE.value,
            },
            "style_reference_filter": {
                "corpus_type": CorpusType.REFERENCE_STYLE.value,
                "allowed_usage": AllowedUsage.STYLE_ONLY.value,
            },
            "allowed_product_evidence_ids": [
                item.evidence_id
                for item in state.evidence_map
                if item.corpus_type == CorpusType.PRODUCT_EVIDENCE
                and item.allowed_usage == AllowedUsage.FACTUAL_EVIDENCE
                and item.evidence_type != EvidenceType.PRODUCT_SCREENSHOT
            ],
            "allowed_reference_style_ids": [
                item.evidence_id
                for item in state.evidence_map
                if item.corpus_type == CorpusType.REFERENCE_STYLE
                and item.allowed_usage == AllowedUsage.STYLE_ONLY
            ],
            "evidence_trace": evidence_trace,
            "writer_must_use_product_evidence": True,
            "writer_must_not_use_reference_as_fact": True,
        }

    @staticmethod
    def _screenshot_policy(state: DocForgeState) -> dict[str, Any]:
        screenshot_ids = [
            item.evidence_id
            for item in state.evidence_map
            if item.evidence_type == EvidenceType.PRODUCT_SCREENSHOT
        ]
        return {
            "screenshot_evidence_ids": screenshot_ids,
            "screenshot_required_for_chapters": [],
            "visual_parse_status": "not_performed",
            "can_use_screenshot_as_strong_evidence": False,
            "can_use_screenshot_as_product_fact": False,
            "screenshot_usage": "figure_placeholder_only",
            "screenshot_binding_status": "not_performed",
        }

    @staticmethod
    def _writing_policy(state: DocForgeState) -> dict[str, Any]:
        from docforge_core.workflow.run_settings import get_run_settings

        run_settings = get_run_settings(state)
        return {
            "writing_style_summary": state.style_profile.writing_style,
            "selected_doc_output_type": run_settings["doc_output_type"],
            "reference_style_strength": run_settings["reference_style_strength"],
            "operation_step_style": state.style_profile.operation_step_pattern,
            "screenshot_caption_style": state.style_profile.screenshot_usage_pattern,
            "forbidden_content_rules": [
                "不得使用 reference_style 作为产品事实",
                "不得把 planned / unknown 写成当前已实现",
                "不得写 unsupported 功能",
                "不得自行发明模块、页面、流程",
                "不得使用宣传式夸大表达",
            ],
            "future_feature_rule": (
                "planned / unknown 只能作为风险或待确认内容，不得写入当前功能章节。"
            ),
            "reference_style_usage_rule": (
                "reference_style 只允许用于目录结构、写法、截图排布、语言风格。"
            ),
        }

    @staticmethod
    def _quality_gate_policy(state: DocForgeState) -> dict[str, Any]:
        return {
            "plan_quality_gate_checklist": [
                "软件名称是否明确",
                "软件版本是否明确",
                "软件类型是否已确认",
                "文档模板是否已冻结",
                "一级目录是否已冻结",
                "是否区分参考资料和自有产品资料",
                "当前功能是否均有 product_evidence",
                "参考资料是否未被当作事实使用",
                "是否存在 planned/unknown 功能被写成当前功能",
                "是否存在必须向用户反问的缺失信息",
            ],
            "draft_quality_gate_rules": [
                "score >= 85",
                "blocker_count = 0",
                "major_count <= 2",
                "产品事实均来自 product_evidence",
                "reference_style 不得作为产品事实",
                "一级目录不得违反 FrozenDocPlan",
                "软件名称和版本号全文一致",
                "planned / unknown 不得写成当前已实现",
            ],
            "max_revision_round": state.max_revision_round,
            "draft_score_threshold": 85,
        }
