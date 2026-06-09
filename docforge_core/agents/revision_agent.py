"""Sprint 12 controlled v2/v3 draft revision."""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from docforge_core.agents.audit_agent import AuditAgentService, EvidenceTextResolver
from docforge_core.domain.enums import (
    AllowedUsage,
    AuditCategory,
    CorpusType,
    DraftQualityGateDecision,
    DraftVersionLabel,
    NextAction,
    WorkflowStatus,
)
from docforge_core.domain.schemas import (
    AuditFinding,
    DocForgeState,
    DraftAuditReport,
    DraftQualityGateReport,
    DraftVersion,
    EvidenceItem,
    SectionPlan,
)
from docforge_core.io.run_paths import get_drafts_dir, get_state_file
from docforge_core.io.state_store import StateStore
from docforge_core.llm.base import LLMMessage, LLMProvider
from docforge_core.llm.prompt_loader import load_prompt


@dataclass
class RevisionInstructions:
    revision_instructions: list[dict[str, Any]]
    affected_sections: list[str]
    allowed_evidence_by_section: dict[str, list[dict[str, Any]]]
    forbidden_changes: list[str]
    required_fixes: list[dict[str, Any]]
    section_scoped_fixes: list[dict[str, Any]] = field(default_factory=list)
    global_fixes: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    instruction_error: str | None = None


@dataclass
class RevisionResult:
    draft: dict[str, Any]
    revision_trace: dict[str, Any]
    changed_sections: list[str]
    fixed_finding_ids: list[str]
    unresolved_finding_ids: list[str]
    evidence_ids_used: list[str]
    validation_result: dict[str, Any]
    global_fixes_applied: list[dict[str, Any]]


GLOBAL_SOFTWARE_IDENTITY_CATEGORIES = {
    AuditCategory.SOFTWARE_IDENTITY_MISMATCH,
    AuditCategory.SOFTWARE_VERSION_MISMATCH,
}


class RevisionInstructionBuilder:
    """Build narrow, section-scoped instructions from failed gate findings."""

    def __init__(self, text_resolver: EvidenceTextResolver) -> None:
        self.text_resolver = text_resolver

    def build(
        self,
        state: DocForgeState,
        current_draft: dict[str, Any],
        audit_report: DraftAuditReport,
        quality_gate_report: DraftQualityGateReport,
    ) -> RevisionInstructions:
        if quality_gate_report.passed:
            raise ValueError("通过的 DraftQualityGate 不应生成修订指令")
        plan_by_id = {item.section_id: item for item in state.section_plan}
        draft_section_ids = set(AuditAgentService.draft_sections_by_id(current_draft))
        evidence_by_id = {item.evidence_id: item for item in state.evidence_map}
        hard_ids = set(quality_gate_report.blocking_finding_ids) | set(
            quality_gate_report.major_finding_ids
        )
        required_fixes: list[dict[str, Any]] = []
        section_scoped_fixes: list[dict[str, Any]] = []
        global_fixes: list[dict[str, Any]] = []
        warnings: list[str] = [
            item.finding_id
            for item in audit_report.findings
            if item.finding_id in set(quality_gate_report.minor_finding_ids)
            | set(quality_gate_report.suggestion_finding_ids)
        ]
        allowed_by_section: dict[str, list[dict[str, Any]]] = {}
        for finding in audit_report.findings:
            if finding.finding_id not in hard_ids:
                continue
            section_id = finding.section_id
            if not section_id and finding.category in GLOBAL_SOFTWARE_IDENTITY_CATEGORIES:
                fix = self._global_fix_item(finding)
                required_fixes.append(fix)
                global_fixes.append(fix)
                continue
            if not section_id or section_id not in plan_by_id or section_id not in draft_section_ids:
                return self._error(f"finding {finding.finding_id} 无法定位到合法章节")
            plan = plan_by_id[section_id]
            allowed_by_section.setdefault(
                section_id,
                self._allowed_evidence_bundle(state, plan, evidence_by_id),
            )
            fix = self._fix_item(finding, plan)
            required_fixes.append(fix)
            section_scoped_fixes.append(fix)

        if not required_fixes and not quality_gate_report.passed:
            return self._error("DraftQualityGate 未通过但没有可执行 required_fixes")
        affected = list(dict.fromkeys(item["section_id"] for item in section_scoped_fixes))
        return RevisionInstructions(
            revision_instructions=required_fixes,
            affected_sections=affected,
            allowed_evidence_by_section=allowed_by_section,
            forbidden_changes=[
                "不得新增 SectionPlan 之外的章节",
                "不得删除 SectionPlan 章节",
                "不得修改一级目录、FrozenDocPlan、DocumentOutline、SectionPlan",
                "不得新增 evidence_id 或伪造 quote",
                "不得修改 figure_slots 或绑定真实截图",
                "不得自行查询 Qdrant 或脑补产品功能",
            ],
            required_fixes=required_fixes,
            section_scoped_fixes=section_scoped_fixes,
            global_fixes=global_fixes,
            warnings=warnings,
        )

    def _allowed_evidence_bundle(
        self,
        state: DocForgeState,
        plan: SectionPlan,
        evidence_by_id: dict[str, EvidenceItem],
    ) -> list[dict[str, Any]]:
        bundle: list[dict[str, Any]] = []
        for evidence_id in plan.required_evidence_ids:
            item = evidence_by_id.get(evidence_id)
            if item is None:
                raise ValueError(f"SectionPlan.required_evidence_ids 引用不存在 evidence: {evidence_id}")
            if (
                item.corpus_type != CorpusType.PRODUCT_EVIDENCE
                or item.allowed_usage != AllowedUsage.FACTUAL_EVIDENCE
            ):
                raise ValueError("RevisionInstructionBuilder 只能下发 product_evidence/factual_evidence")
            text = self.text_resolver.text_for_quote_check(state, item)
            quote = self._first_quote(state, item, text)
            bundle.append(
                {
                    "evidence_id": item.evidence_id,
                    "source_id": item.source_id,
                    "summary": item.summary,
                    "quote": quote,
                    "text": text,
                }
            )
        return bundle

    @staticmethod
    def _first_quote(state: DocForgeState, item: EvidenceItem, text: str) -> str:
        trace = state.frozen_doc_plan.evidence_policy.get("evidence_trace", []) if state.frozen_doc_plan else []
        for trace_item in trace:
            if isinstance(trace_item, dict) and trace_item.get("evidence_id") == item.evidence_id:
                quote = trace_item.get("quote")
                if isinstance(quote, str) and quote.strip():
                    return quote
        return item.summary or text[:200]

    @staticmethod
    def _fix_item(finding: AuditFinding, plan: SectionPlan) -> dict[str, Any]:
        return {
            "scope": "section",
            "finding_id": finding.finding_id,
            "severity": finding.severity.value,
            "category": finding.category.value,
            "section_id": plan.section_id,
            "section_path": list(plan.section_path),
            "message": finding.message,
            "claim_text": finding.claim_text,
            "evidence_id": finding.evidence_id,
            "quote": finding.quote,
            "recommendation": finding.recommendation,
        }

    @staticmethod
    def _global_fix_item(finding: AuditFinding) -> dict[str, Any]:
        return {
            "scope": "global",
            "finding_id": finding.finding_id,
            "severity": finding.severity.value,
            "category": finding.category.value,
            "message": finding.message,
            "claim_text": finding.claim_text,
            "evidence_id": finding.evidence_id,
            "quote": finding.quote,
            "recommendation": finding.recommendation,
        }

    @staticmethod
    def _error(message: str) -> RevisionInstructions:
        return RevisionInstructions(
            revision_instructions=[],
            affected_sections=[],
            allowed_evidence_by_section={},
            forbidden_changes=[],
            required_fixes=[],
            section_scoped_fixes=[],
            global_fixes=[],
            instruction_error=message,
        )


class RevisedDraftValidator:
    """Fail closed before draft_v2/v3 is written."""

    def __init__(self, text_resolver: EvidenceTextResolver) -> None:
        self.text_resolver = text_resolver

    def validate(
        self,
        state: DocForgeState,
        original_draft: dict[str, Any],
        revised_draft: dict[str, Any],
        target_version: int,
        figure_slots_before: dict[str, Any],
    ) -> dict[str, Any]:
        expected_label = f"v{target_version}"
        previous_label = f"v{target_version - 1}"
        if revised_draft.get("version_label") != expected_label:
            raise ValueError("修订稿 version_label 不正确")
        if revised_draft.get("previous_version") != previous_label:
            raise ValueError("修订稿 previous_version 不正确")
        if "figure_slots" in revised_draft:
            raise ValueError("DraftVersion 中不得写入 figure_slots")
        if not isinstance(figure_slots_before.get("figure_slots"), list):
            raise ValueError("figure_slots_v1.json 结构不合法")
        self._validate_container(original_draft, revised_draft)
        plan_by_id = {item.section_id: item for item in state.section_plan}
        evidence_by_id = {item.evidence_id: item for item in state.evidence_map}
        sections = AuditAgentService.draft_sections_by_id(revised_draft)
        if set(sections) != set(plan_by_id):
            raise ValueError("修订稿 section 集合必须与 SectionPlan 完全一致")
        evidence_ids_used: set[str] = set()
        for section_id, section in sections.items():
            plan = plan_by_id[section_id]
            if section.get("section_path") != plan.section_path:
                raise ValueError("修订稿 section_path 必须来自 SectionPlan")
            used = section.get("evidence_ids_used", [])
            if not isinstance(used, list):
                raise ValueError("evidence_ids_used 必须是 list")
            if not set(map(str, used)).issubset(set(plan.required_evidence_ids)):
                raise ValueError("evidence_ids_used 出现 SectionPlan 之外的 evidence")
            evidence_ids_used.update(map(str, used))
            self._validate_citations(state, plan, section, evidence_by_id)
        self._validate_software_identity(state, revised_draft)
        return {
            "passed": True,
            "target_version": expected_label,
            "validated_section_count": len(sections),
            "evidence_ids_used": sorted(evidence_ids_used),
        }

    @staticmethod
    def _validate_container(original: dict[str, Any], revised: dict[str, Any]) -> None:
        original_titles = [str(item.get("title", "")) for item in original.get("chapters", [])]
        revised_titles = [str(item.get("title", "")) for item in revised.get("chapters", [])]
        if original_titles != revised_titles:
            raise ValueError("一级目录不得变化")
        if not isinstance(revised.get("chapters"), list) or not revised["chapters"]:
            raise ValueError("修订稿 chapters 必须是非空 list")

    def _validate_citations(
        self,
        state: DocForgeState,
        plan: SectionPlan,
        section: dict[str, Any],
        evidence_by_id: dict[str, EvidenceItem],
    ) -> None:
        citations = section.get("citations", [])
        if not isinstance(citations, list):
            raise ValueError("citations 必须是 list")
        for citation in citations:
            if not isinstance(citation, dict):
                raise ValueError("citation 必须是 object")
            evidence_id = citation.get("evidence_id")
            quote = citation.get("quote")
            if not isinstance(evidence_id, str) or evidence_id not in plan.required_evidence_ids:
                raise ValueError("citation.evidence_id 必须属于 SectionPlan.required_evidence_ids")
            if not isinstance(quote, str) or not quote.strip():
                raise ValueError("citation.quote 不得为空")
            evidence = evidence_by_id.get(evidence_id)
            if evidence is None:
                raise ValueError("citation.evidence_id 不存在于 evidence_map")
            if (
                evidence.corpus_type != CorpusType.PRODUCT_EVIDENCE
                or evidence.allowed_usage != AllowedUsage.FACTUAL_EVIDENCE
            ):
                raise ValueError("修订稿不得引用 reference_style 或非 factual_evidence")
            if self._normalize(quote) not in self._normalize(
                self.text_resolver.text_for_quote_check(state, evidence)
            ):
                raise ValueError("citation.quote 不存在于对应 evidence 文本")

    @staticmethod
    def _validate_software_identity(state: DocForgeState, draft: dict[str, Any]) -> None:
        if state.frozen_doc_plan is None:
            return
        expected = state.frozen_doc_plan.software_identity
        if not expected:
            return
        actual = draft.get("software_identity")
        if not isinstance(actual, dict):
            raise ValueError("修订稿必须携带 software_identity")
        for key in ("target_product_name", "software_name", "version"):
            if expected.get(key) and actual.get(key) != expected.get(key):
                raise ValueError("修订稿 software_identity 必须与 FrozenDocPlan 一致")
        metadata = draft.get("metadata")
        if isinstance(metadata, dict) and "software_identity" in metadata:
            metadata_identity = metadata.get("software_identity")
            if not isinstance(metadata_identity, dict):
                raise ValueError("修订稿 metadata.software_identity 必须是 object")
            for key in ("target_product_name", "software_name", "version"):
                if expected.get(key) and metadata_identity.get(key) != expected.get(key):
                    raise ValueError("修订稿 metadata.software_identity 必须与 FrozenDocPlan 一致")

    @staticmethod
    def _normalize(value: str) -> str:
        return "".join(value.split())


class DraftRevisionAgent:
    """Create draft_v2/v3 from a failed audit/gate pair."""

    def __init__(
        self,
        state_store: StateStore | None = None,
        llm_provider: LLMProvider | None = None,
    ) -> None:
        self.state_store = state_store or StateStore()
        self.llm_provider = llm_provider
        self.text_resolver = EvidenceTextResolver(self.state_store.data_dir)
        self.builder = RevisionInstructionBuilder(self.text_resolver)
        self.validator = RevisedDraftValidator(self.text_resolver)

    def revise_current_draft(self, run_id: str) -> RevisionResult:
        state = self.state_store.load_state(run_id)
        if state.workflow_status != WorkflowStatus.DRAFT_REVISION_REQUIRED:
            raise ValueError("RevisionAgent 要求 workflow_status 为 DRAFT_REVISION_REQUIRED")
        if state.next_action != NextAction.REVISE_DRAFT:
            raise ValueError("RevisionAgent 要求 next_action 为 REVISE_DRAFT")
        current_version = self._current_draft_number(state)
        if current_version >= 3:
            raise ValueError("v3 不允许继续修订")
        target_version = current_version + 1
        drafts_dir = get_drafts_dir(run_id, self.state_store.data_dir)
        current_path = drafts_dir / f"draft_v{current_version}.json"
        target_path = drafts_dir / f"draft_v{target_version}.json"
        audit_path = drafts_dir / f"audit_report_v{current_version}.json"
        gate_path = drafts_dir / f"quality_gate_report_v{current_version}.json"
        figure_path = drafts_dir / "figure_slots_v1.json"
        if target_path.exists():
            raise ValueError(f"draft_v{target_version}.json 已存在，不允许覆盖")

        current_draft = self._load_object(current_path, f"draft_v{current_version}.json")
        audit_report = DraftAuditReport.model_validate(
            self._load_object(audit_path, f"audit_report_v{current_version}.json")
        )
        gate_report = DraftQualityGateReport.model_validate(
            self._load_object(gate_path, f"quality_gate_report_v{current_version}.json")
        )
        figure_slots = self._load_object(figure_path, "figure_slots_v1.json")
        self._validate_revision_inputs_bound(
            state=state,
            current_version=current_version,
            current_path=current_path,
            figure_path=figure_path,
            audit_path=audit_path,
            gate_path=gate_path,
            audit_report=audit_report,
            gate_report=gate_report,
        )
        lineage = self._revision_lineage(
            current_version,
            audit_report,
            gate_report,
            gate_path,
        )
        instructions = self.builder.build(state, current_draft, audit_report, gate_report)
        if instructions.instruction_error:
            raise ValueError(instructions.instruction_error)
        if instructions.affected_sections and self.llm_provider is None:
            raise ValueError("RevisionAgent 处理章节修订要求 llm_provider")
        revised = self._generate_revised_draft(
            state,
            current_draft,
            instructions,
            current_version,
            target_version,
            lineage,
        )
        validation = self.validator.validate(
            state,
            current_draft,
            revised["draft"],
            target_version,
            figure_slots,
        )
        revised["validation_result"] = validation
        self._write_and_update_state(
            state,
            target_path,
            drafts_dir / f"revision_trace_v{target_version}.json",
            revised,
            current_version,
            target_version,
        )
        return RevisionResult(**revised)

    def _generate_revised_draft(
        self,
        state: DocForgeState,
        current_draft: dict[str, Any],
        instructions: RevisionInstructions,
        current_version: int,
        target_version: int,
        lineage: dict[str, Any],
    ) -> dict[str, Any]:
        draft = copy.deepcopy(current_draft)
        draft["draft_id"] = f"draft_{state.run_id}_v{target_version}"
        draft["version_label"] = f"v{target_version}"
        draft["previous_version"] = f"v{current_version}"
        draft["created_at"] = datetime.now(UTC).isoformat()
        global_fixes_applied = self._apply_global_fixes(state, draft, instructions.global_fixes)
        self._ensure_software_identity_from_plan(state, draft)
        sections = AuditAgentService.draft_sections_by_id(draft)
        plan_by_id = {item.section_id: item for item in state.section_plan}
        changed_sections: list[str] = []
        fixed: list[str] = [item["finding_id"] for item in global_fixes_applied]
        unresolved: list[str] = []
        evidence_ids_used: set[str] = set()
        for section_id in instructions.affected_sections:
            section = sections[section_id]
            plan = plan_by_id[section_id]
            fixes = [
                item
                for item in instructions.section_scoped_fixes
                if item["section_id"] == section_id
            ]
            allowed = instructions.allowed_evidence_by_section[section_id]
            response = self._revise_section(state, section, plan, fixes, allowed)
            section["content"] = str(response["content"])
            section["evidence_ids_used"] = list(response["evidence_ids_used"])
            section["citations"] = list(response["citations"])
            section.setdefault("warnings", []).extend(response.get("warnings", []))
            changed_sections.append(section_id)
            fixed.extend(map(str, response.get("fixed_finding_ids", [])))
            unresolved.extend(map(str, response.get("unresolved_finding_ids", [])))
            evidence_ids_used.update(map(str, response["evidence_ids_used"]))
        return {
            "draft": draft,
            "revision_trace": {
                "from_version": f"v{current_version}",
                "to_version": f"v{target_version}",
                **lineage,
                "required_fixes": instructions.required_fixes,
                "section_scoped_fixes": instructions.section_scoped_fixes,
                "global_fixes": instructions.global_fixes,
                "forbidden_changes": instructions.forbidden_changes,
            },
            "changed_sections": changed_sections,
            "fixed_finding_ids": list(dict.fromkeys(fixed)),
            "unresolved_finding_ids": list(dict.fromkeys(unresolved)),
            "evidence_ids_used": sorted(evidence_ids_used),
            "validation_result": {},
            "global_fixes_applied": global_fixes_applied,
        }

    @staticmethod
    def _apply_global_fixes(
        state: DocForgeState,
        draft: dict[str, Any],
        global_fixes: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        if not global_fixes:
            return []
        if state.frozen_doc_plan is None or not state.frozen_doc_plan.software_identity:
            raise ValueError("全局软件身份修订要求 FrozenDocPlan.software_identity")
        software_identity = copy.deepcopy(state.frozen_doc_plan.software_identity)
        applied: list[dict[str, Any]] = []
        for fix in global_fixes:
            category = AuditCategory(fix["category"])
            if category not in GLOBAL_SOFTWARE_IDENTITY_CATEGORIES:
                raise ValueError("不支持的 global_fixes category")
            applied.append(
                {
                    "finding_id": fix["finding_id"],
                    "category": category.value,
                    "action": "set_software_identity_from_frozen_doc_plan",
                }
            )
        draft["software_identity"] = software_identity
        metadata = draft.get("metadata")
        if isinstance(metadata, dict) and "software_identity" in metadata:
            metadata["software_identity"] = copy.deepcopy(software_identity)
        return applied

    @staticmethod
    def _ensure_software_identity_from_plan(
        state: DocForgeState,
        draft: dict[str, Any],
    ) -> None:
        if state.frozen_doc_plan is None or not state.frozen_doc_plan.software_identity:
            return
        software_identity = copy.deepcopy(state.frozen_doc_plan.software_identity)
        draft["software_identity"] = software_identity
        metadata = draft.get("metadata")
        if isinstance(metadata, dict) and "software_identity" in metadata:
            metadata["software_identity"] = copy.deepcopy(software_identity)

    def _revise_section(
        self,
        state: DocForgeState,
        section: dict[str, Any],
        plan: SectionPlan,
        fixes: list[dict[str, Any]],
        allowed_evidence: list[dict[str, Any]],
    ) -> dict[str, Any]:
        assert self.llm_provider is not None
        payload = {
            "current_section_content": section.get("content", ""),
            "finding_list": fixes,
            "revision_instruction": "只修复 finding_list 中的问题，不改章节结构。",
            "allowed_evidence_bundle": [
                {k: item[k] for k in ("evidence_id", "source_id", "summary", "quote")}
                for item in allowed_evidence
            ],
            "writing_constraints": plan.writing_constraints,
            "section_plan_projection": {
                "section_id": plan.section_id,
                "section_title": plan.section_title,
                "section_path": plan.section_path,
                "required_evidence_ids": plan.required_evidence_ids,
            },
            "frozen_doc_plan_summary": {
                "software_identity": state.frozen_doc_plan.software_identity
                if state.frozen_doc_plan
                else {},
                "writing_policy": state.frozen_doc_plan.writing_policy
                if state.frozen_doc_plan
                else {},
            },
        }
        response = self.llm_provider.generate_json(
            [
                LLMMessage(role="system", content=load_prompt("writer_revision_section.md")),
                LLMMessage(role="user", content=json.dumps(payload, ensure_ascii=False, indent=2)),
            ]
        )
        if not isinstance(response.get("content"), str):
            raise ValueError("RevisionAgent LLM 输出缺少 content")
        if not isinstance(response.get("evidence_ids_used"), list):
            raise ValueError("RevisionAgent LLM 输出缺少 evidence_ids_used")
        if not isinstance(response.get("citations"), list):
            raise ValueError("RevisionAgent LLM 输出缺少 citations")
        allowed_ids = {item["evidence_id"] for item in allowed_evidence}
        if not set(map(str, response["evidence_ids_used"])).issubset(allowed_ids):
            raise ValueError("RevisionAgent LLM 输出伪造 evidence_id")
        for citation in response["citations"]:
            if not isinstance(citation, dict) or citation.get("evidence_id") not in allowed_ids:
                raise ValueError("RevisionAgent LLM 输出非法 citation")
        return response

    def _write_and_update_state(
        self,
        state: DocForgeState,
        target_path: Path,
        trace_path: Path,
        result: dict[str, Any],
        current_version: int,
        target_version: int,
    ) -> None:
        state_path = get_state_file(state.run_id, self.state_store.data_dir)
        original_state = state_path.read_bytes()
        tmp_path = target_path.with_suffix(target_path.suffix + ".tmp")
        trace_tmp_path = trace_path.with_suffix(trace_path.suffix + ".tmp")
        if tmp_path.exists():
            tmp_path.unlink()
        if trace_tmp_path.exists():
            trace_tmp_path.unlink()
        if trace_path.exists():
            raise ValueError(f"revision_trace_v{target_version}.json 已存在，不允许覆盖")
        try:
            tmp_path.write_text(
                json.dumps(result["draft"], ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            trace_payload = self._trace_payload(result, current_version, target_version)
            trace_tmp_path.write_text(
                json.dumps(trace_payload, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            tmp_path.replace(target_path)
            trace_tmp_path.replace(trace_path)
            version_label = DraftVersionLabel(f"v{target_version}")
            draft_version = DraftVersion(
                draft_id=result["draft"]["draft_id"],
                version_label=version_label,
                based_on_plan_id=result["draft"].get("based_on_plan_id", ""),
                based_on_outline_id=result["draft"].get("based_on_outline_id", ""),
                content_ref=f"drafts/draft_v{target_version}.json",
                revision_notes=f"controlled revision from v{current_version}",
                source_audit_report_id=f"audit_v{current_version}_{state.run_id}",
            )
            state.draft_versions.append(draft_version)
            state.current_draft_id = draft_version.draft_id
            state.current_draft_version = draft_version.version_label.value
            state.revision_round += 1
            state.workflow_status = (
                WorkflowStatus.DRAFT_V2_CREATED
                if target_version == 2
                else WorkflowStatus.DRAFT_V3_CREATED
            )
            state.next_action = NextAction.AUDIT_REVISED_DRAFT
            self.state_store.save_state(state)
        except Exception:
            if tmp_path.exists():
                tmp_path.unlink()
            if trace_tmp_path.exists():
                trace_tmp_path.unlink()
            if target_path.exists():
                target_path.unlink()
            if trace_path.exists():
                trace_path.unlink()
            self._restore_state_file(state_path, original_state)
            raise

    def _validate_revision_inputs_bound(
        self,
        *,
        state: DocForgeState,
        current_version: int,
        current_path: Path,
        figure_path: Path,
        audit_path: Path,
        gate_path: Path,
        audit_report: DraftAuditReport,
        gate_report: DraftQualityGateReport,
    ) -> None:
        expected_version = f"v{current_version}"
        expected_audit_ref = f"drafts/audit_report_v{current_version}.json"
        expected_gate_ref = f"drafts/quality_gate_report_v{current_version}.json"
        expected_draft_ref = f"drafts/draft_v{current_version}.json"
        expected_figure_ref = "drafts/figure_slots_v1.json"

        if audit_report.draft_version != expected_version:
            raise ValueError("audit_report draft_version 与当前修订版本不匹配")
        if audit_report.source_draft_ref != expected_draft_ref:
            raise ValueError("audit_report source_draft_ref 与当前修订版本不匹配")
        if audit_report.source_figure_slots_ref != expected_figure_ref:
            raise ValueError("audit_report source_figure_slots_ref 与当前修订版本不匹配")
        if audit_report.source_draft_hash != self.sha256(current_path):
            raise ValueError("audit_report source_draft_hash 不匹配")
        if audit_report.source_figure_slots_hash != self.sha256(figure_path):
            raise ValueError("audit_report source_figure_slots_hash 不匹配")
        if not audit_report.report_id.strip():
            raise ValueError("audit_report report_id 不得为空")
        if state.audit_report_ref != expected_audit_ref:
            raise ValueError("state.audit_report_ref 与当前 audit_report 不匹配")
        if state.audit_report_result_id != audit_report.report_id:
            raise ValueError("state.audit_report_result_id 与 audit_report 不匹配")
        self._validate_audit_report_consistency(audit_report)

        if gate_report.draft_version != expected_version:
            raise ValueError("quality_gate_report draft_version 与当前修订版本不匹配")
        if gate_report.source_audit_report_path != expected_audit_ref:
            raise ValueError("quality_gate_report source_audit_report_path 不匹配")
        if gate_report.source_audit_report_hash != self.sha256(audit_path):
            raise ValueError("quality_gate_report source_audit_report_hash 不匹配")
        if gate_report.source_draft_ref != audit_report.source_draft_ref:
            raise ValueError("quality_gate_report source_draft_ref 与 audit_report 不匹配")
        if gate_report.source_figure_slots_ref != audit_report.source_figure_slots_ref:
            raise ValueError(
                "quality_gate_report source_figure_slots_ref 与 audit_report 不匹配"
            )
        if gate_report.source_draft_hash != audit_report.source_draft_hash:
            raise ValueError("quality_gate_report source_draft_hash 与 audit_report 不匹配")
        if gate_report.source_figure_slots_hash != audit_report.source_figure_slots_hash:
            raise ValueError(
                "quality_gate_report source_figure_slots_hash 与 audit_report 不匹配"
            )
        if gate_report.source_draft_hash != self.sha256(current_path):
            raise ValueError("quality_gate_report source_draft_hash 不匹配")
        if gate_report.source_figure_slots_hash != self.sha256(figure_path):
            raise ValueError("quality_gate_report source_figure_slots_hash 不匹配")
        if state.draft_quality_gate_report_ref != expected_gate_ref:
            raise ValueError("state.draft_quality_gate_report_ref 与当前 gate report 不匹配")
        if not gate_path.exists():
            raise ValueError("quality_gate_report 文件缺失")
        if gate_report.audit_overall_passed != audit_report.overall_passed:
            raise ValueError("quality_gate_report audit_overall_passed 与 audit_report 不匹配")

        if gate_report.passed is not False:
            raise ValueError("RevisionAgent 只能消费未通过的 DraftQualityGate")
        if gate_report.decision != DraftQualityGateDecision.REQUIRE_REVISION:
            raise ValueError("RevisionAgent 只能消费 require_revision gate report")
        if gate_report.next_workflow_status != WorkflowStatus.DRAFT_REVISION_REQUIRED:
            raise ValueError("quality_gate_report next_workflow_status 不允许修订")
        if gate_report.next_action != NextAction.REVISE_DRAFT:
            raise ValueError("quality_gate_report next_action 不允许修订")

        expected_ids = self._finding_ids_by_severity(audit_report)
        if set(gate_report.blocking_finding_ids) != expected_ids["blocker"]:
            raise ValueError("quality_gate_report blocking_finding_ids 与 audit_report 不匹配")
        if set(gate_report.major_finding_ids) != expected_ids["major"]:
            raise ValueError("quality_gate_report major_finding_ids 与 audit_report 不匹配")
        if set(gate_report.minor_finding_ids) != expected_ids["minor"]:
            raise ValueError("quality_gate_report minor_finding_ids 与 audit_report 不匹配")
        if set(gate_report.suggestion_finding_ids) != expected_ids["suggestion"]:
            raise ValueError("quality_gate_report suggestion_finding_ids 与 audit_report 不匹配")

        counts = gate_report.severity_counts
        if (
            counts.blocker != len(expected_ids["blocker"])
            or counts.major != len(expected_ids["major"])
            or counts.minor != len(expected_ids["minor"])
            or counts.suggestion != len(expected_ids["suggestion"])
        ):
            raise ValueError("quality_gate_report severity_counts 与 audit_report 不匹配")

    @staticmethod
    def _validate_audit_report_consistency(report: DraftAuditReport) -> None:
        ids_by_severity = DraftRevisionAgent._finding_ids_by_severity(report)
        summary = report.summary
        if (
            summary.blocker_count != len(ids_by_severity["blocker"])
            or summary.major_count != len(ids_by_severity["major"])
            or summary.minor_count != len(ids_by_severity["minor"])
            or summary.suggestion_count != len(ids_by_severity["suggestion"])
            or summary.total_findings != len(report.findings)
        ):
            raise ValueError("audit_report summary 与 findings 不一致，RevisionAgent fail closed")
        if report.overall_passed != (summary.blocker_count == 0):
            raise ValueError(
                "audit_report overall_passed 与 findings 不一致，RevisionAgent fail closed"
            )

    @staticmethod
    def _finding_ids_by_severity(report: DraftAuditReport) -> dict[str, set[str]]:
        return {
            "blocker": {
                item.finding_id for item in report.findings if item.severity.value == "blocker"
            },
            "major": {
                item.finding_id for item in report.findings if item.severity.value == "major"
            },
            "minor": {
                item.finding_id for item in report.findings if item.severity.value == "minor"
            },
            "suggestion": {
                item.finding_id
                for item in report.findings
                if item.severity.value == "suggestion"
            },
        }

    @staticmethod
    def _trace_payload(
        result: dict[str, Any],
        current_version: int,
        target_version: int,
    ) -> dict[str, Any]:
        trace = dict(result["revision_trace"])
        trace.update(
            {
                "from_version": f"v{current_version}",
                "to_version": f"v{target_version}",
                "fixed_finding_ids": result["fixed_finding_ids"],
                "unresolved_finding_ids": result["unresolved_finding_ids"],
                "changed_sections": result["changed_sections"],
                "global_fixes_applied": result["global_fixes_applied"],
                "evidence_ids_used": result["evidence_ids_used"],
                "validation_result": result["validation_result"],
                "created_at": datetime.now(UTC).isoformat(),
            }
        )
        return trace

    def _revision_lineage(
        self,
        current_version: int,
        audit_report: DraftAuditReport,
        gate_report: DraftQualityGateReport,
        gate_path: Path,
    ) -> dict[str, str]:
        return {
            "source_draft_ref": audit_report.source_draft_ref,
            "source_draft_hash": audit_report.source_draft_hash,
            "source_figure_slots_ref": audit_report.source_figure_slots_ref,
            "source_figure_slots_hash": audit_report.source_figure_slots_hash,
            "source_audit_report_ref": gate_report.source_audit_report_path,
            "source_audit_report_hash": gate_report.source_audit_report_hash,
            "source_quality_gate_report_ref": (
                f"drafts/quality_gate_report_v{current_version}.json"
            ),
            "source_quality_gate_report_hash": self.sha256(gate_path),
        }

    @staticmethod
    def _current_draft_number(state: DocForgeState) -> int:
        if state.current_draft_version in {"v1", "v2", "v3"}:
            return int(state.current_draft_version[1])
        raise ValueError("无法确定当前修订源版本")

    @staticmethod
    def _load_object(path: Path, name: str) -> dict[str, Any]:
        if not path.exists():
            raise ValueError(f"{name} 缺失")
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise ValueError(f"{name} 无法解析") from exc
        if not isinstance(value, dict):
            raise ValueError(f"{name} 必须是 JSON 对象")
        return value

    @staticmethod
    def sha256(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    @staticmethod
    def _restore_state_file(state_path: Path, original: bytes) -> None:
        rollback = state_path.with_suffix(".json.revision_rollback.tmp")
        try:
            rollback.write_bytes(original)
            rollback.replace(state_path)
        finally:
            if rollback.exists():
                rollback.unlink()
