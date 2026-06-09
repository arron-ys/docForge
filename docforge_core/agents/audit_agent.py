"""Audit draft_v1 deterministically and semantically without modifying inputs."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from docforge_core.domain.enums import (
    AllowedUsage,
    AuditCategory,
    AuditSeverity,
    CorpusType,
    EvidenceType,
    NextAction,
    WorkflowStatus,
)
from docforge_core.domain.schemas import (
    AuditFinding,
    AuditReportSummary,
    AuditSafetyReport,
    AuditSectionSummary,
    DocForgeState,
    DraftAuditReport,
    EvidenceItem,
    FigureSlotResult,
    SectionPlan,
)
from docforge_core.io.run_paths import get_drafts_dir, get_run_dir, get_state_file
from docforge_core.io.state_store import StateStore
from docforge_core.llm.base import LLMMessage, LLMProvider
from docforge_core.llm.prompt_loader import load_prompt

from ._shared import transition
from .outline_validator import OutlineValidator

FORBIDDEN_FIGURE_FIELDS = {
    "screenshot_file_path",
    "screenshot_source_id",
    "image_path",
    "asset_id",
    "existing_screenshot",
    "matched_screenshot",
    "bound_screenshot",
    "real_screenshot",
    "uploaded_image",
}
SEMANTIC_CATEGORIES = {
    AuditCategory.CLAIM_NOT_SUPPORTED_BY_QUOTE,
    AuditCategory.PLANNED_WRITTEN_AS_CURRENT,
    AuditCategory.UNKNOWN_WRITTEN_AS_CURRENT,
    AuditCategory.UNSUPPORTED_CAPABILITY_CLAIM,
    AuditCategory.EXAGGERATED_CLAIM,
    AuditCategory.STYLE_DEVIATION,
    AuditCategory.FIGURE_SLOT_SEMANTIC_MISMATCH,
}
MAX_QUOTE_CONTENT_BYTES = 512_000


def _normalize_text(value: str) -> str:
    return "".join(value.split())


def _safe_section_path(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    return []


class EvidenceTextResolver:
    """Resolve deterministic quote-check text without trusting metadata."""

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir

    def text_for_quote_check(self, state: DocForgeState, evidence: EvidenceItem) -> str:
        parts: list[str] = [evidence.summary or "", evidence.notes or ""]
        parts.extend(self._strings_from_value(evidence.extracted_facts))
        content_text = self._read_content_ref(state, evidence)
        if content_text:
            parts.append(content_text)
        return "\n".join(parts)

    @classmethod
    def _strings_from_value(cls, value: Any) -> list[str]:
        if isinstance(value, str):
            return [value]
        if isinstance(value, dict):
            result: list[str] = []
            for child in value.values():
                result.extend(cls._strings_from_value(child))
            return result
        if isinstance(value, list):
            list_result: list[str] = []
            for child in value:
                list_result.extend(cls._strings_from_value(child))
            return list_result
        return []

    def _read_content_ref(self, state: DocForgeState, evidence: EvidenceItem) -> str:
        if not evidence.content_ref or evidence.evidence_type == EvidenceType.PRODUCT_SCREENSHOT:
            return ""
        run_dir = get_run_dir(state.run_id, self.data_dir).resolve()
        raw_path = Path(evidence.content_ref)
        candidate = raw_path if raw_path.is_absolute() else run_dir / raw_path
        try:
            resolved = candidate.resolve()
        except OSError:
            return ""
        if not resolved.is_relative_to(run_dir):
            return ""
        if not resolved.exists() or not resolved.is_file():
            return ""
        data = resolved.read_bytes()[:MAX_QUOTE_CONTENT_BYTES]
        return data.decode("utf-8", errors="ignore")


class DeterministicDraftAuditor:
    """Perform structural, citation, and evidence-isolation checks."""

    def __init__(self, text_resolver: EvidenceTextResolver) -> None:
        self.text_resolver = text_resolver

    def audit(
        self,
        state: DocForgeState,
        draft: dict[str, Any],
        draft_version: int = 1,
    ) -> list[AuditFinding]:
        findings: list[AuditFinding] = []
        findings.extend(self._audit_draft_container_schema(state, draft, draft_version))
        draft_sections = AuditAgentService.draft_sections_by_id(draft)
        plan_by_id = {item.section_id: item for item in state.section_plan}
        evidence_by_id = {item.evidence_id: item for item in state.evidence_map}
        findings.extend(self._audit_software_identity(state, draft))
        findings.extend(self._audit_section_schema(draft))
        findings.extend(self._audit_feature_policy(state))

        try:
            assert state.outline is not None
            assert state.frozen_doc_plan is not None
            OutlineValidator().validate_outline(state.outline, state.frozen_doc_plan)
        except Exception as exc:
            findings.append(
                self._finding(
                    AuditSeverity.BLOCKER,
                    AuditCategory.PLAN_VIOLATION,
                    f"FrozenDocPlan 与 Outline 不一致：{exc}",
                    "恢复与 FrozenDocPlan 一致的一级目录和大纲后重新生成草稿。",
                )
            )

        for section_id in plan_by_id.keys() - draft_sections.keys():
            plan = plan_by_id[section_id]
            findings.append(
                self._finding(
                    AuditSeverity.MAJOR,
                    AuditCategory.SECTION_MISSING,
                    "SectionPlan 中的章节未出现在草稿中。",
                    "补齐该章节正文。",
                    plan,
                )
            )
        for section_id in draft_sections.keys() - plan_by_id.keys():
            section = draft_sections[section_id]
            findings.append(
                self._finding(
                    AuditSeverity.MAJOR,
                    AuditCategory.SECTION_NOT_IN_PLAN,
                    "草稿包含 SectionPlan 之外的章节。",
                    "删除额外章节或先更新并重新冻结文档计划。",
                    section=section,
                )
            )

        for section_id in draft_sections.keys() & plan_by_id.keys():
            section = draft_sections[section_id]
            plan = plan_by_id[section_id]
            if (
                section.get("section_title") != plan.section_title
                or section.get("section_path") != plan.section_path
            ):
                findings.append(
                    self._finding(
                        AuditSeverity.MAJOR,
                        AuditCategory.SECTION_METADATA_MISMATCH,
                        "草稿章节标题或路径与 SectionPlan 不一致。",
                        "按 SectionPlan 恢复章节标题和路径。",
                        plan,
                    )
                )
            findings.extend(self._audit_section_evidence(state, section, plan, evidence_by_id))
        return findings

    def _audit_draft_container_schema(
        self,
        state: DocForgeState,
        draft: dict[str, Any],
        draft_version: int,
    ) -> list[AuditFinding]:
        findings: list[AuditFinding] = []
        if draft.get("version_label") != f"v{draft_version}":
            findings.append(
                self._container_schema_finding(
                    f"draft.version_label 必须存在且等于 v{draft_version}。"
                )
            )
        if draft_version > 1 and draft.get("previous_version") != f"v{draft_version - 1}":
            findings.append(
                self._container_schema_finding(
                    f"draft.previous_version 必须存在且等于 v{draft_version - 1}。"
                )
            )
        chapters = draft.get("chapters")
        if "chapters" not in draft or not isinstance(chapters, list):
            findings.append(self._container_schema_finding("draft.chapters 必须存在且是 list。"))
            return findings
        if not chapters and state.section_plan:
            findings.append(self._container_schema_finding("draft.chapters 不得为空。"))
        seen_section_ids: set[str] = set()
        for chapter in chapters:
            if not isinstance(chapter, dict):
                findings.append(self._container_schema_finding("每个 chapter 必须是 object。"))
                continue
            sections = chapter.get("sections")
            if "sections" not in chapter or not isinstance(sections, list):
                findings.append(self._container_schema_finding("chapter.sections 必须存在且是 list。"))
                continue
            for section in sections:
                if not isinstance(section, dict):
                    findings.append(self._container_schema_finding("chapter.sections 中每个 section 必须是 object。"))
                    continue
                section_id = section.get("section_id")
                if isinstance(section_id, str) and section_id.strip():
                    if section_id in seen_section_ids:
                        findings.append(self._container_schema_finding(f"section_id 重复: {section_id}。"))
                    seen_section_ids.add(section_id)
        return findings

    def _audit_section_schema(self, draft: dict[str, Any]) -> list[AuditFinding]:
        findings: list[AuditFinding] = []
        for section in AuditAgentService.draft_sections(draft):
            if not isinstance(section.get("section_id"), str) or not section.get("section_id", "").strip():
                findings.append(self._schema_finding("section 缺少 section_id 或 section_id 非空字符串。", section))
            if not isinstance(section.get("section_title"), str) or not section.get("section_title", "").strip():
                findings.append(self._schema_finding("section 缺少 section_title 或 section_title 非空字符串。", section))
            if "section_path" not in section or not isinstance(section.get("section_path"), list):
                findings.append(self._schema_finding("section 缺少 section_path 或 section_path 不是 list。", section))
            if "content" not in section or not isinstance(section.get("content"), str):
                findings.append(self._schema_finding("section 缺少 content 或 content 不是 string。", section))
            if "evidence_ids_used" not in section or not isinstance(section.get("evidence_ids_used"), list):
                findings.append(self._schema_finding("evidence_ids_used 缺失或不是 list。", section))
            if "citations" not in section or not isinstance(section.get("citations"), list):
                findings.append(self._schema_finding("citations 缺失或不是 list。", section))
            citations = section.get("citations")
            if isinstance(citations, list):
                for citation in citations:
                    if not isinstance(citation, dict):
                        findings.append(self._schema_finding("citation 必须是 object。", section))
                        continue
                    if not isinstance(citation.get("evidence_id"), str) or not citation.get("evidence_id", "").strip():
                        findings.append(self._schema_finding("citation.evidence_id 缺失或不是非空 string。", section))
                    if not isinstance(citation.get("quote"), str) or not citation.get("quote", "").strip():
                        findings.append(self._schema_finding("citation.quote 缺失或不是非空 string。", section))
        return findings

    def _audit_feature_policy(self, state: DocForgeState) -> list[AuditFinding]:
        if state.frozen_doc_plan is None:
            return []
        policy = state.frozen_doc_plan.feature_policy
        planned = self._ids_from_policy(policy.get("planned_capabilities", []))
        unknown = self._ids_from_policy(policy.get("unknown_capabilities", []))
        unsupported = self._ids_from_policy(policy.get("unsupported_capabilities", []))
        unsupported.update(self._ids_from_policy(policy.get("unsupported_or_rejected_features", [])))
        findings: list[AuditFinding] = []
        for plan in state.section_plan:
            required = set(plan.required_capability_ids)
            if required.intersection(planned):
                findings.append(self._finding(AuditSeverity.BLOCKER, AuditCategory.PLANNED_WRITTEN_AS_CURRENT, "SectionPlan.required_capability_ids 包含 planned capability。", "移除 planned 能力或先补充当前版本证据并重新冻结计划。", plan))
            if required.intersection(unknown):
                findings.append(self._finding(AuditSeverity.BLOCKER, AuditCategory.UNKNOWN_WRITTEN_AS_CURRENT, "SectionPlan.required_capability_ids 包含 unknown capability。", "移除 unknown 能力或先补充当前版本证据并重新冻结计划。", plan))
            if required.intersection(unsupported):
                findings.append(self._finding(AuditSeverity.BLOCKER, AuditCategory.UNSUPPORTED_CAPABILITY_CLAIM, "SectionPlan.required_capability_ids 包含 unsupported capability。", "移除 unsupported 能力或重新完成证据确认。", plan))
            if plan.needs_human_confirmation:
                findings.append(self._finding(AuditSeverity.MAJOR, AuditCategory.PLAN_VIOLATION, "该章节仍需人工确认，但草稿已生成正文。", "先补充产品事实证据并重新确认后再生成正文。", plan))
        return findings

    @staticmethod
    def _ids_from_policy(values: Any) -> set[str]:
        if not isinstance(values, list):
            return set()
        result: set[str] = set()
        for item in values:
            if isinstance(item, dict) and item.get("capability_id"):
                result.add(str(item["capability_id"]))
        return result

    def _audit_software_identity(self, state: DocForgeState, draft: dict[str, Any]) -> list[AuditFinding]:
        if state.frozen_doc_plan is None:
            return []
        expected = state.frozen_doc_plan.software_identity
        expected_name = str(expected.get("target_product_name") or expected.get("software_name") or "")
        expected_version = str(expected.get("version") or "")
        actual = self._draft_software_identity(draft)
        if not actual:
            return [
                self._finding(
                    AuditSeverity.SUGGESTION,
                    AuditCategory.SOFTWARE_IDENTITY_MISSING,
                    "draft schema 当前未显式携带软件名称/版本，后续 Writer/Exporter 需要统一注入。",
                    "在后续正文或导出阶段统一注入 FrozenDocPlan.software_identity。",
                )
            ]
        findings: list[AuditFinding] = []
        actual_name = str(actual.get("target_product_name") or actual.get("software_name") or "")
        actual_version = str(actual.get("version") or "")
        if expected_name and actual_name and actual_name != expected_name:
            findings.append(self._finding(AuditSeverity.BLOCKER, AuditCategory.SOFTWARE_IDENTITY_MISMATCH, "draft 软件名称与 FrozenDocPlan 不一致。", "按 FrozenDocPlan.software_identity 恢复软件名称。"))
        if expected_version and actual_version and actual_version != expected_version:
            findings.append(self._finding(AuditSeverity.MAJOR, AuditCategory.SOFTWARE_VERSION_MISMATCH, "draft 软件版本与 FrozenDocPlan 不一致。", "按 FrozenDocPlan.software_identity 恢复软件版本。"))
        return findings

    @staticmethod
    def _draft_software_identity(draft: dict[str, Any]) -> dict[str, Any]:
        for key in ("software_identity",):
            value = draft.get(key)
            if isinstance(value, dict):
                return value
        metadata = draft.get("metadata")
        if isinstance(metadata, dict) and isinstance(metadata.get("software_identity"), dict):
            return metadata["software_identity"]
        result = {}
        for key in ("target_product_name", "software_name", "version"):
            if key in draft:
                result[key] = draft[key]
        return result

    def _audit_section_evidence(
        self,
        state: DocForgeState,
        section: dict[str, Any],
        plan: SectionPlan,
        evidence_by_id: dict[str, EvidenceItem],
    ) -> list[AuditFinding]:
        findings: list[AuditFinding] = []
        required_ids = set(plan.required_evidence_ids)
        used_ids = section.get("evidence_ids_used", [])
        if not isinstance(used_ids, list):
            return findings
        for evidence_id in used_ids:
            evidence_id = str(evidence_id)
            evidence = evidence_by_id.get(evidence_id)
            if evidence is None:
                findings.append(
                    self._evidence_finding(
                        AuditCategory.EVIDENCE_ID_NOT_FOUND,
                        "正文使用的 evidence_id 不存在于 evidence_map。",
                        plan,
                        evidence_id,
                    )
                )
                continue
            if evidence_id not in required_ids:
                findings.append(
                    self._evidence_finding(
                        AuditCategory.EVIDENCE_ID_OUT_OF_SECTION_PLAN,
                        "正文使用的 evidence_id 超出 SectionPlan.required_evidence_ids。",
                        plan,
                        evidence_id,
                    )
                )
            findings.extend(self._audit_evidence_isolation(evidence, plan, evidence_id))

        citations = section.get("citations", [])
        if not isinstance(citations, list):
            return findings
        for citation in citations:
            if not isinstance(citation, dict):
                continue
            raw_evidence_id = citation.get("evidence_id")
            raw_quote = citation.get("quote")
            if not isinstance(raw_evidence_id, str) or not raw_evidence_id.strip():
                continue
            if not isinstance(raw_quote, str) or not raw_quote.strip():
                continue
            evidence_id = raw_evidence_id
            quote = raw_quote
            evidence = evidence_by_id.get(evidence_id)
            if evidence is None:
                findings.append(
                    self._evidence_finding(
                        AuditCategory.EVIDENCE_ID_NOT_FOUND,
                        "citation.evidence_id 不存在于 evidence_map。",
                        plan,
                        evidence_id,
                        quote,
                    )
                )
                continue
            if evidence_id not in required_ids:
                findings.append(
                    self._evidence_finding(
                        AuditCategory.CITATION_OUT_OF_SECTION_PLAN,
                        "citation.evidence_id 超出 SectionPlan.required_evidence_ids。",
                        plan,
                        evidence_id,
                        quote,
                    )
                )
            findings.extend(self._audit_evidence_isolation(evidence, plan, evidence_id, quote))
            if not quote.strip() or _normalize_text(quote) not in _normalize_text(
                self.text_resolver.text_for_quote_check(state, evidence)
            ):
                findings.append(
                    self._evidence_finding(
                        AuditCategory.CITATION_QUOTE_NOT_FOUND,
                        "正文引用的 quote 在对应 evidence 原文中不存在。",
                        plan,
                        evidence_id,
                        quote,
                    )
                )
            source_id = citation.get("source_id")
            if source_id is not None and source_id != evidence.source_id:
                findings.append(
                    self._evidence_finding(
                        AuditCategory.CITATION_QUOTE_NOT_FOUND,
                        "citation.source_id 与 evidence_map 不一致。",
                        plan,
                        evidence_id,
                        quote,
                    )
                )
        return findings

    def _audit_evidence_isolation(
        self,
        evidence: EvidenceItem,
        plan: SectionPlan,
        evidence_id: str,
        quote: str | None = None,
    ) -> list[AuditFinding]:
        findings: list[AuditFinding] = []
        if evidence.corpus_type == CorpusType.REFERENCE_STYLE:
            findings.append(
                self._evidence_finding(
                    AuditCategory.REFERENCE_STYLE_USED_AS_FACT,
                    "reference_style evidence 被当作产品事实使用。",
                    plan,
                    evidence_id,
                    quote,
                )
            )
        if evidence.allowed_usage != AllowedUsage.FACTUAL_EVIDENCE:
            findings.append(
                self._evidence_finding(
                    AuditCategory.NON_FACTUAL_EVIDENCE_USED_AS_FACT,
                    "allowed_usage 非 factual_evidence 的 evidence 被当作事实使用。",
                    plan,
                    evidence_id,
                    quote,
                )
            )
        return findings

    @staticmethod
    def _schema_finding(message: str, section: dict[str, Any]) -> AuditFinding:
        return DeterministicDraftAuditor._finding(
            AuditSeverity.BLOCKER,
            AuditCategory.DRAFT_SCHEMA_INVALID,
            message,
            "重新生成符合 WriterAgent 结构契约的 draft_v1.json。",
            section=section,
        )

    @staticmethod
    def _container_schema_finding(message: str) -> AuditFinding:
        return DeterministicDraftAuditor._finding(
            AuditSeverity.BLOCKER,
            AuditCategory.DRAFT_SCHEMA_INVALID,
            message,
            "修复 draft_v1.json 顶层、chapter 与 section 容器结构后重新审计。",
        )

    @staticmethod
    def _evidence_finding(
        category: AuditCategory,
        message: str,
        plan: SectionPlan,
        evidence_id: str,
        quote: str | None = None,
    ) -> AuditFinding:
        return DeterministicDraftAuditor._finding(
            AuditSeverity.BLOCKER,
            category,
            message,
            "删除不合法引用，或改用该章节允许且可真实定位的 product evidence。",
            plan,
            evidence_id=evidence_id or None,
            quote=quote,
        )

    @staticmethod
    def _finding(
        severity: AuditSeverity,
        category: AuditCategory,
        message: str,
        recommendation: str,
        plan: SectionPlan | None = None,
        *,
        section: dict[str, Any] | None = None,
        evidence_id: str | None = None,
        quote: str | None = None,
    ) -> AuditFinding:
        return AuditFinding(
            finding_id="pending",
            severity=severity,
            category=category,
            section_id=plan.section_id if plan else str((section or {}).get("section_id", "")) or None,
            section_path=plan.section_path if plan else _safe_section_path((section or {}).get("section_path")),
            message=message,
            evidence_id=evidence_id,
            quote=quote,
            recommendation=recommendation,
            detector="deterministic",
        )


class FigureSlotAuditor:
    """Audit raw FigureSlotResult without trusting its schema."""

    def audit(
        self,
        raw: dict[str, Any],
        draft_section_ids: set[str],
        section_plan: list[SectionPlan],
    ) -> list[AuditFinding]:
        findings: list[AuditFinding] = []
        plan_by_id = {item.section_id: item for item in section_plan}
        slots = raw.get("figure_slots", [])
        if not isinstance(slots, list):
            return [self._invalid("figure_slots 必须是数组。")]
        try:
            FigureSlotResult.model_validate(raw)
        except ValidationError as exc:
            findings.append(self._invalid(f"figure_slots_v1.json schema 不合法：{exc}"))
        for slot in slots:
            if not isinstance(slot, dict):
                findings.append(self._invalid("figure slot 必须是对象。"))
                continue
            section_id = str(slot.get("section_id", ""))
            plan = plan_by_id.get(section_id)
            if section_id not in draft_section_ids or plan is None:
                findings.append(
                    self._finding(
                        AuditSeverity.MAJOR,
                        AuditCategory.FIGURE_SLOT_SECTION_NOT_FOUND,
                        section_id,
                        _safe_section_path(slot.get("section_path")),
                        "figure slot.section_id 不存在于草稿或 SectionPlan。",
                        "删除无效图位或将其绑定到真实存在的章节。",
                    )
                )
            elif slot.get("section_path") != plan.section_path:
                findings.append(self._invalid("figure slot.section_path 与 SectionPlan 不一致。", plan))
            if not str(slot.get("recommended_caption", "")).strip():
                findings.append(self._invalid("recommended_caption 不得为空。", plan))
            if not str(slot.get("user_action", "")).strip():
                findings.append(self._invalid("user_action 不得为空。", plan))
            if slot.get("status") != "missing":
                findings.append(
                    self._finding(
                        AuditSeverity.BLOCKER,
                        AuditCategory.FIGURE_SLOT_CLAIMS_EXISTING_IMAGE,
                        section_id,
                        _safe_section_path(slot.get("section_path")),
                        "figure slot.status 必须为 missing，不得声称已有截图。",
                        "将图位恢复为 missing，仅保留补图建议。",
                    )
                )
            for key in FORBIDDEN_FIGURE_FIELDS:
                if key in slot:
                    findings.append(
                        self._finding(
                            AuditSeverity.BLOCKER,
                            AuditCategory.FIGURE_SLOT_CLAIMS_EXISTING_IMAGE,
                            section_id,
                            _safe_section_path(slot.get("section_path")),
                            f"figure slot 包含真实截图绑定字段：{key}。",
                            "删除真实截图绑定字段，仅保留补图建议。",
                        )
                    )
        return findings

    @staticmethod
    def _invalid(message: str, plan: SectionPlan | None = None) -> AuditFinding:
        return FigureSlotAuditor._finding(
            AuditSeverity.BLOCKER,
            AuditCategory.FIGURE_SLOT_INVALID,
            plan.section_id if plan else None,
            plan.section_path if plan else [],
            message,
            "修复 figure_slots_v1.json 的结构后重新审计。",
        )

    @staticmethod
    def _finding(
        severity: AuditSeverity,
        category: AuditCategory,
        section_id: str | None,
        section_path: list[str],
        message: str,
        recommendation: str,
    ) -> AuditFinding:
        return AuditFinding(
            finding_id="pending",
            severity=severity,
            category=category,
            section_id=section_id,
            section_path=section_path,
            message=message,
            recommendation=recommendation,
            detector="deterministic",
        )


class SemanticDraftAuditVerifier:
    """Run evidence-scoped semantic auditing and validate every LLM finding."""

    def __init__(
        self,
        llm_provider: LLMProvider | None,
        text_resolver: EvidenceTextResolver,
    ) -> None:
        self.llm_provider = llm_provider
        self.text_resolver = text_resolver

    def audit(
        self,
        state: DocForgeState,
        draft: dict[str, Any],
        figure_slots: dict[str, Any],
    ) -> list[AuditFinding]:
        if self.llm_provider is None:
            return [self.failed("LLMProvider 不可用，语义审计未完成。")]
        evidence_by_id = {item.evidence_id: item for item in state.evidence_map}
        plan_by_id = {item.section_id: item for item in state.section_plan}
        slots_by_section: dict[str, list[dict[str, Any]]] = {}
        for slot in self._safe_figure_slots(figure_slots):
            slots_by_section.setdefault(str(slot.get("section_id", "")), []).append(slot)

        findings: list[AuditFinding] = []
        for section_id, section in AuditAgentService.draft_sections_by_id(draft).items():
            plan = plan_by_id.get(section_id)
            if plan is None:
                continue
            payload = self._payload(
                state,
                section,
                plan,
                slots_by_section.get(section_id, []),
                evidence_by_id,
            )
            try:
                response = self.llm_provider.generate_json(
                    [
                        LLMMessage(role="system", content=load_prompt("audit.md")),
                        LLMMessage(role="user", content=json.dumps(payload, ensure_ascii=False, indent=2)),
                    ]
                )
                findings.extend(
                    self._validate_response(response, state, section, plan, evidence_by_id)
                )
            except Exception as exc:
                findings.append(self.failed(f"语义审计失败：{exc}", plan))
        return findings

    @staticmethod
    def _safe_figure_slots(raw: dict[str, Any]) -> list[dict[str, Any]]:
        slots = raw.get("figure_slots", [])
        if not isinstance(slots, list):
            return []
        return [slot for slot in slots if isinstance(slot, dict)]

    def _payload(
        self,
        state: DocForgeState,
        section: dict[str, Any],
        plan: SectionPlan,
        slots: list[dict[str, Any]],
        evidence_by_id: dict[str, EvidenceItem],
    ) -> dict[str, Any]:
        evidence = []
        for evidence_id in plan.required_evidence_ids:
            item = evidence_by_id.get(evidence_id)
            if item is None or item.corpus_type != CorpusType.PRODUCT_EVIDENCE:
                continue
            evidence.append(
                {
                    "evidence_id": item.evidence_id,
                    "source_id": item.source_id,
                    "summary": item.summary,
                    "text": self.text_resolver.text_for_quote_check(state, item),
                    "needs_human_confirmation": item.needs_human_confirmation,
                }
            )
        frozen = state.frozen_doc_plan
        feature_policy = frozen.feature_policy if frozen else {}
        return {
            "task": "return structured audit findings only; never rewrite the draft",
            "section": {
                "section_id": plan.section_id,
                "section_title": plan.section_title,
                "section_path": plan.section_path,
                "content": section.get("content", ""),
                "citations": section.get("citations", []),
            },
            "section_plan": plan.model_dump(mode="json"),
            "allowed_product_evidence": evidence,
            "figure_slots": slots,
            "document_constraints": {
                "software_identity": frozen.software_identity if frozen else {},
                "writing_policy": frozen.writing_policy if frozen else {},
                "feature_policy": {
                    key: feature_policy.get(key, [])
                    for key in (
                        "current_capabilities",
                        "planned_capabilities",
                        "unknown_capabilities",
                        "unsupported_or_rejected_features",
                        "allowed_current_feature_names",
                        "forbidden_as_current_feature_names",
                        "current_facts",
                    )
                },
            },
            "output_schema": {
                "findings": [
                    {
                        "severity": "blocker|major|minor|suggestion",
                        "category": "allowed semantic category",
                        "section_id": plan.section_id,
                        "message": "string",
                        "claim_text": "string or null",
                        "evidence_id": "string or null",
                        "quote": "string or null",
                        "recommendation": "string",
                        "confidence": "0..1",
                    }
                ]
            },
        }

    def _validate_response(
        self,
        response: dict[str, Any],
        state: DocForgeState,
        section: dict[str, Any],
        plan: SectionPlan,
        evidence_by_id: dict[str, EvidenceItem],
    ) -> list[AuditFinding]:
        raw_findings = response.get("findings")
        if not isinstance(raw_findings, list):
            raise ValueError("语义审计输出缺少 findings 数组")
        findings: list[AuditFinding] = []
        content = str(section.get("content", ""))
        required_ids = set(plan.required_evidence_ids)
        for raw in raw_findings:
            if not isinstance(raw, dict):
                raise ValueError("语义 finding 必须是对象")
            raw_severity = raw.get("severity")
            raw_category = raw.get("category")
            if not isinstance(raw_severity, str) or not isinstance(raw_category, str):
                raise ValueError("语义 finding severity/category 必须是字符串")
            severity = AuditSeverity(raw_severity)
            category = AuditCategory(raw_category)
            if category not in SEMANTIC_CATEGORIES:
                raise ValueError("语义 finding category 不允许")
            if raw.get("section_id") != plan.section_id:
                raise ValueError("语义 finding section_id 不合法")
            claim_text = raw.get("claim_text")
            if claim_text and str(claim_text) not in content:
                raise ValueError("语义 finding claim_text 不存在于 section content")
            evidence_id = raw.get("evidence_id")
            quote = raw.get("quote")
            if quote and not evidence_id:
                raise ValueError("语义 finding quote 非空时 evidence_id 必须非空")
            if evidence_id:
                evidence_id = str(evidence_id)
                if evidence_id not in required_ids:
                    raise ValueError("语义 finding evidence_id 超出 SectionPlan")
                evidence = evidence_by_id.get(evidence_id)
                if evidence is None:
                    raise ValueError("语义 finding evidence_id 不存在")
                if quote and _normalize_text(str(quote)) not in _normalize_text(
                    self.text_resolver.text_for_quote_check(state, evidence)
                ):
                    raise ValueError("语义 finding quote 不存在于 evidence")
            findings.append(
                AuditFinding(
                    finding_id="pending",
                    severity=severity,
                    category=category,
                    section_id=plan.section_id,
                    section_path=plan.section_path,
                    message=str(raw.get("message", "")).strip(),
                    claim_text=str(claim_text) if claim_text else None,
                    evidence_id=evidence_id,
                    quote=str(quote) if quote else None,
                    recommendation=str(raw.get("recommendation", "")).strip(),
                    detector="semantic_llm",
                    metadata={"confidence": raw.get("confidence")},
                )
            )
            if not findings[-1].message or not findings[-1].recommendation:
                raise ValueError("语义 finding message/recommendation 不得为空")
        return findings

    @staticmethod
    def failed(message: str, plan: SectionPlan | None = None) -> AuditFinding:
        return AuditFinding(
            finding_id="pending",
            severity=AuditSeverity.BLOCKER,
            category=AuditCategory.SEMANTIC_VERIFIER_FAILED,
            section_id=plan.section_id if plan else None,
            section_path=plan.section_path if plan else [],
            message=message,
            recommendation="修复语义审计服务或非法输出后重新审计。",
            detector="validator",
        )


class AuditReportValidator:
    """Validate report statistics, safety flags, and pass computation."""

    def validate(self, report: DraftAuditReport) -> None:
        expected = AuditAgentService.report_summary(
            report.findings,
            report.summary.audited_section_count,
            report.summary.figure_slot_count,
        )
        if report.summary != expected:
            raise ValueError("DraftAuditReport summary 统计不准确")
        if report.overall_passed != (report.summary.blocker_count == 0):
            raise ValueError("DraftAuditReport overall_passed 计算不准确")
        checks = report.safety_report.model_dump(mode="json")
        if any(value is not True for key, value in checks.items() if key != "warnings"):
            raise ValueError("DraftAuditReport safety_report 未通过")


class AuditAgentService:
    """Create drafts/audit_report_vN.json and advance to DraftQualityGate."""

    def __init__(
        self,
        state_store: StateStore | None = None,
        llm_provider: LLMProvider | None = None,
    ) -> None:
        self.state_store = state_store or StateStore()
        self.text_resolver = EvidenceTextResolver(self.state_store.data_dir)
        self.deterministic = DeterministicDraftAuditor(self.text_resolver)
        self.semantic = SemanticDraftAuditVerifier(llm_provider, self.text_resolver)
        self.figure_auditor = FigureSlotAuditor()
        self.validator = AuditReportValidator()

    def audit_draft(self, run_id: str, draft_version: int | None = None) -> DraftAuditReport:
        state = self.state_store.load_state(run_id)
        version = draft_version or self._current_draft_number(state)
        self._require_ready_state(state, version)
        drafts_dir = get_drafts_dir(run_id, self.state_store.data_dir)
        draft_path = drafts_dir / f"draft_v{version}.json"
        figure_path = drafts_dir / "figure_slots_v1.json"
        audit_path = drafts_dir / f"audit_report_v{version}.json"
        tmp_path = drafts_dir / f"audit_report_v{version}.json.tmp"
        state_path = get_state_file(run_id, self.state_store.data_dir)
        original_state = state_path.read_bytes()
        if tmp_path.exists():
            tmp_path.unlink()
        if not draft_path.exists():
            raise ValueError(f"AuditAgent 要求存在 drafts/draft_v{version}.json")
        if not figure_path.exists():
            raise ValueError("AuditAgent 要求存在 drafts/figure_slots_v1.json")
        if audit_path.exists():
            if version == 1 and state.audit_report_ref is None:
                raise ValueError("存在未被 state 承认的 stale audit_report_v1.json")
            raise ValueError(f"草稿已经审计，不允许重复覆盖 audit_report_v{version}.json")

        draft_hash = self.sha256(draft_path)
        figure_hash = self.sha256(figure_path)
        draft_versions_before = [item.model_dump(mode="json") for item in state.draft_versions]
        draft = self._load_object(draft_path, "draft_v1.json")
        figures = self._load_object(figure_path, "figure_slots_v1.json")
        findings = self.deterministic.audit(state, draft, version)
        findings.extend(
            self.figure_auditor.audit(
                figures,
                set(self.draft_sections_by_id(draft)),
                state.section_plan,
            )
        )
        findings.extend(self.semantic.audit(state, draft, figures))
        self.assign_finding_ids(findings)
        report = self.build_report(
            state,
            draft,
            figures,
            findings,
            version,
            source_draft_hash=draft_hash,
            source_figure_slots_hash=figure_hash,
        )
        self.validator.validate(report)

        try:
            self._assert_inputs_unchanged(
                draft_path,
                figure_path,
                draft_hash,
                figure_hash,
                state,
                draft_versions_before,
            )
            tmp_path.write_text(
                json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            tmp_path.replace(audit_path)
            self._assert_inputs_unchanged(
                draft_path,
                figure_path,
                draft_hash,
                figure_hash,
                state,
                draft_versions_before,
            )
            state.audit_report_ref = f"drafts/audit_report_v{version}.json"
            state.audit_report_result_id = report.report_id
            from_status = state.workflow_status
            to_status = self._audited_status(version)
            transition(
                state,
                from_status,
                to_status,
                NextAction.RUN_DRAFT_QUALITY_GATE,
                "AuditAgentService.audit_draft",
                f"v{version} draft audit completed",
            )
            self.state_store.save_state(state)
            saved = self.state_store.load_state(run_id)
            self._validate_success_state(saved, report, audit_path, version, to_status)
        except Exception:
            if tmp_path.exists():
                tmp_path.unlink()
            if audit_path.exists():
                audit_path.unlink()
            self.restore_state_file(state_path, original_state)
            raise
        return report

    @staticmethod
    def _require_ready_state(state: DocForgeState, draft_version: int) -> None:
        if draft_version == 1:
            normal = (
                state.workflow_status == WorkflowStatus.FIGURE_SLOTS_PLANNED
                and state.next_action == NextAction.AUDIT_DRAFT
            )
            compatible = (
                state.workflow_status == WorkflowStatus.DRAFT_V1_CREATED
                and state.next_action == NextAction.AUDIT_DRAFT
                and state.figure_slots_ref == "drafts/figure_slots_v1.json"
            )
            if not (normal or compatible):
                raise ValueError(
                    "AuditAgent 要求 FIGURE_SLOTS_PLANNED/AUDIT_DRAFT，"
                    "或带合法 figure_slots_ref 的 DRAFT_V1_CREATED/AUDIT_DRAFT"
                )
        elif draft_version == 2:
            if not (
                state.workflow_status == WorkflowStatus.DRAFT_V2_CREATED
                and state.next_action == NextAction.AUDIT_REVISED_DRAFT
            ):
                raise ValueError("AuditAgent 审计 v2 要求 DRAFT_V2_CREATED/AUDIT_REVISED_DRAFT")
        elif draft_version == 3:
            if not (
                state.workflow_status == WorkflowStatus.DRAFT_V3_CREATED
                and state.next_action == NextAction.AUDIT_REVISED_DRAFT
            ):
                raise ValueError("AuditAgent 审计 v3 要求 DRAFT_V3_CREATED/AUDIT_REVISED_DRAFT")
        else:
            raise ValueError("AuditAgent 只支持 draft_version 1/2/3")
        if state.frozen_doc_plan is None or state.outline is None or not state.section_plan:
            raise ValueError("AuditAgent 要求 FrozenDocPlan、Outline 和 SectionPlan")
        if not any(item.version_label.value == f"v{draft_version}" for item in state.draft_versions):
            raise ValueError(f"AuditAgent 要求 state.draft_versions 中存在 v{draft_version}")
        if state.figure_slots_ref != "drafts/figure_slots_v1.json":
            raise ValueError("AuditAgent 要求 figure_slots_ref 指向 drafts/figure_slots_v1.json")

    @staticmethod
    def _current_draft_number(state: DocForgeState) -> int:
        if state.current_draft_version in {"v1", "v2", "v3"}:
            return int(state.current_draft_version[1])
        return 1

    @staticmethod
    def _load_object(path: Path, name: str) -> dict[str, Any]:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise ValueError(f"{name} 无法解析") from exc
        if not isinstance(value, dict):
            raise ValueError(f"{name} 必须是 JSON 对象")
        return value

    @staticmethod
    def draft_sections_by_id(draft: dict[str, Any]) -> dict[str, dict[str, Any]]:
        sections: dict[str, dict[str, Any]] = {}
        for section in AuditAgentService.draft_sections(draft):
            if section.get("section_id"):
                sections[str(section["section_id"])] = section
        return sections

    @staticmethod
    def draft_sections(draft: dict[str, Any]) -> list[dict[str, Any]]:
        sections: list[dict[str, Any]] = []
        chapters = draft.get("chapters", [])
        if not isinstance(chapters, list):
            return sections
        for chapter in chapters:
            if not isinstance(chapter, dict):
                continue
            raw_sections = chapter.get("sections", [])
            if not isinstance(raw_sections, list):
                continue
            for section in raw_sections:
                if isinstance(section, dict):
                    sections.append(section)
        return sections

    @staticmethod
    def assign_finding_ids(findings: list[AuditFinding]) -> None:
        for index, finding in enumerate(findings, start=1):
            finding.finding_id = f"audit_finding_{index:03d}"

    @classmethod
    def build_report(
        cls,
        state: DocForgeState,
        draft: dict[str, Any],
        figures: dict[str, Any],
        findings: list[AuditFinding],
        draft_version: int = 1,
        *,
        source_draft_hash: str,
        source_figure_slots_hash: str,
    ) -> DraftAuditReport:
        sections = cls.draft_sections_by_id(draft)
        slots = figures.get("figure_slots", [])
        slot_count = len(slots) if isinstance(slots, list) else 0
        summary = cls.report_summary(findings, len(sections), slot_count)
        return DraftAuditReport(
            report_id=f"audit_v{draft_version}_{state.run_id}",
            draft_version=f"v{draft_version}",  # type: ignore[arg-type]
            source_draft_ref=f"drafts/draft_v{draft_version}.json",
            source_draft_hash=source_draft_hash,
            source_figure_slots_ref="drafts/figure_slots_v1.json",
            source_figure_slots_hash=source_figure_slots_hash,
            created_at=datetime.now(UTC).isoformat(),
            overall_passed=summary.blocker_count == 0,
            findings=findings,
            section_summaries=cls.section_summaries(state.section_plan, findings),
            summary=summary,
            safety_report=AuditSafetyReport(),
        )

    @staticmethod
    def report_summary(
        findings: list[AuditFinding],
        section_count: int,
        figure_slot_count: int,
    ) -> AuditReportSummary:
        return AuditReportSummary(
            total_findings=len(findings),
            blocker_count=sum(item.severity == AuditSeverity.BLOCKER for item in findings),
            major_count=sum(item.severity == AuditSeverity.MAJOR for item in findings),
            minor_count=sum(item.severity == AuditSeverity.MINOR for item in findings),
            suggestion_count=sum(item.severity == AuditSeverity.SUGGESTION for item in findings),
            audited_section_count=section_count,
            figure_slot_count=figure_slot_count,
        )

    @staticmethod
    def section_summaries(
        section_plan: list[SectionPlan],
        findings: list[AuditFinding],
    ) -> list[AuditSectionSummary]:
        result: list[AuditSectionSummary] = []
        for plan in section_plan:
            related = [item for item in findings if item.section_id == plan.section_id]
            result.append(
                AuditSectionSummary(
                    section_id=plan.section_id,
                    section_title=plan.section_title,
                    blocker_count=sum(item.severity == AuditSeverity.BLOCKER for item in related),
                    major_count=sum(item.severity == AuditSeverity.MAJOR for item in related),
                    minor_count=sum(item.severity == AuditSeverity.MINOR for item in related),
                    suggestion_count=sum(
                        item.severity == AuditSeverity.SUGGESTION for item in related
                    ),
                )
            )
        return result

    @staticmethod
    def sha256(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    @classmethod
    def _assert_inputs_unchanged(
        cls,
        draft_path: Path,
        figure_path: Path,
        draft_hash: str,
        figure_hash: str,
        state: DocForgeState,
        draft_versions_before: list[dict[str, Any]],
    ) -> None:
        if cls.sha256(draft_path) != draft_hash:
            raise ValueError("AuditAgent 执行期间 draft 文件发生变化")
        if cls.sha256(figure_path) != figure_hash:
            raise ValueError("AuditAgent 执行期间 figure_slots_v1.json 发生变化")
        if [item.model_dump(mode="json") for item in state.draft_versions] != draft_versions_before:
            raise ValueError("AuditAgent 不得修改 draft_versions")

    @staticmethod
    def restore_state_file(state_path: Path, original: bytes) -> None:
        rollback = state_path.with_suffix(".json.audit_rollback.tmp")
        try:
            rollback.write_bytes(original)
            rollback.replace(state_path)
        finally:
            if rollback.exists():
                rollback.unlink()

    @staticmethod
    def _validate_success_state(
        state: DocForgeState,
        report: DraftAuditReport,
        audit_path: Path,
        draft_version: int = 1,
        expected_status: WorkflowStatus = WorkflowStatus.DRAFT_AUDITED,
    ) -> None:
        if not audit_path.exists():
            raise ValueError(f"AuditAgent 成功状态缺少 audit_report_v{draft_version}.json")
        if state.audit_report_ref != f"drafts/audit_report_v{draft_version}.json":
            raise ValueError("AuditAgent 成功状态 audit_report_ref 不正确")
        if state.audit_report_result_id != report.report_id:
            raise ValueError("AuditAgent 成功状态 audit_report_result_id 不正确")
        if state.workflow_status != expected_status:
            raise ValueError("AuditAgent 成功状态 workflow_status 不正确")
        if state.next_action != NextAction.RUN_DRAFT_QUALITY_GATE:
            raise ValueError("AuditAgent 成功状态 next_action 不正确")

    @staticmethod
    def _audited_status(draft_version: int) -> WorkflowStatus:
        if draft_version == 1:
            return WorkflowStatus.DRAFT_AUDITED
        if draft_version == 2:
            return WorkflowStatus.DRAFT_V2_AUDITED
        if draft_version == 3:
            return WorkflowStatus.DRAFT_V3_AUDITED
        raise ValueError("AuditAgent 只支持 draft_version 1/2/3")
