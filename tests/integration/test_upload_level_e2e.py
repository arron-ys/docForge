from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
from docx import Document

from docforge_core.agents.audit_agent import AuditAgentService
from docforge_core.agents.figure_slot_planner import FigureSlotPlannerService
from docforge_core.agents.frozen_doc_plan_service import FrozenDocPlanService
from docforge_core.agents.human_confirm_gate import HumanConfirmGate
from docforge_core.agents.outline_agent import OutlineAgent
from docforge_core.agents.product_understanding_agent import ProductUnderstandingAgent
from docforge_core.agents.reference_style_agent import ReferenceStyleAgent
from docforge_core.agents.revision_loop_service import RevisionLoopService
from docforge_core.agents.software_diagnosis_agent import SoftwareDiagnosisAgent
from docforge_core.agents.template_strategy_agent import TemplateStrategyAgent
from docforge_core.agents.understanding_pipeline_service import UnderstandingPipelineService
from docforge_core.domain.enums import (
    EvidenceType,
    ImplementationStatus,
    NextAction,
    ParseStatus,
    SourceType,
    WorkflowStatus,
)
from docforge_core.domain.schemas import DocForgeState
from docforge_core.evidence.extractor import EvidenceExtractorService
from docforge_core.exporters.docx_exporter import DocxExportService, docx_has_embedded_media
from docforge_core.gates.plan_quality_gate import PlanQualityGate
from docforge_core.io.file_registry import SourceFileRegistry
from docforge_core.io.run_paths import get_run_dir
from docforge_core.io.state_store import StateStore
from docforge_core.llm.base import LLMMessage, LLMProvider, LLMResponse
from docforge_core.parsers.source_parsing_service import SourceParsingService
from docforge_core.workflow import WorkflowOrchestratorService, WorkflowServiceRegistry
from docforge_core.workflow.e2e_sample_runner import (
    default_e2e_sample_dir,
    load_e2e_sample_project,
)

CURRENT_QUOTE = "当前版本明确支持用户登录、项目看板、文档上传、资料解析、文档草稿生成、DOCX 导出"
PLANNED_MULTI_TENANT_QUOTE = "多租户协作属于规划能力，不属于当前版本功能"
PLANNED_COMMENT_QUOTE = "在线评论属于规划能力，不属于当前版本功能"
PLANNED_SCREENSHOT_QUOTE = "截图自动识别暂未实现"


class PassingWritingPlanSafetyVerifier:
    def verify_items(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            {
                "item_index": item["item_index"],
                "safe": True,
                "risk_type": "none",
                "reason": "deterministic e2e verifier",
            }
            for item in items
        ]


class Sprint15SampleProvider(LLMProvider):
    """Prompt-aware deterministic provider for the upload-level sample E2E."""

    def generate_text(
        self,
        messages: list[LLMMessage],
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        return LLMResponse(content="{}", model="sprint15-sample", provider="test")

    def generate_json(
        self,
        messages: list[LLMMessage],
        temperature: float = 0.1,
        max_tokens: int | None = None,
    ) -> dict[str, Any]:
        payload = self._payload(messages)
        if isinstance(payload, list):
            return {
                "writing_style": "用户操作手册型软著文档，语言客观、克制。",
                "screenshot_usage_pattern": "在核心功能章节后给出缺图占位。",
                "operation_step_pattern": "按入口、操作、结果描述。",
                "common_chapter_structure": [{"title": "核心功能说明"}],
                "reusable_outline_pattern": [{"title": "用户操作流程"}],
                "prohibited_content_warning": ["reference_style 不得作为产品事实。"],
            }
        if not isinstance(payload, dict):
            return {}
        if "evidence_packets" in payload:
            return self._product_understanding(payload["evidence_packets"])
        if "candidates" in payload:
            return self._accept_candidates(payload["candidates"])
        if "entities" in payload:
            return self._accept_entities(payload["entities"])
        if "items" in payload:
            return {
                "results": [
                    {
                        "item_index": item["item_index"],
                        "safe": True,
                        "risk_type": "none",
                        "reason": "safe",
                    }
                    for item in payload["items"]
                ]
            }
        if "section_draft" in payload:
            return {
                "safe": True,
                "risk_type": "none",
                "reason": "section draft is evidence-scoped",
                "offending_spans": [],
            }
        if "section_plan" in payload and "evidence_bundle" in payload:
            return self._section_draft(payload)
        if payload.get("task") and "section" in payload:
            return {"findings": []}
        return {"findings": []}

    @staticmethod
    def _payload(messages: list[LLMMessage]) -> Any:
        try:
            return json.loads(messages[1].content)
        except Exception:
            return {}

    def _product_understanding(self, packets: list[dict[str, Any]]) -> dict[str, Any]:
        current_evidence_id = self._evidence_id_for_quote(packets, CURRENT_QUOTE)
        multi_tenant_id = self._evidence_id_for_quote(packets, PLANNED_MULTI_TENANT_QUOTE)
        comment_id = self._evidence_id_for_quote(packets, PLANNED_COMMENT_QUOTE)
        screenshot_auto_id = self._evidence_id_for_quote(packets, PLANNED_SCREENSHOT_QUOTE)
        if not current_evidence_id:
            return {"capabilities": [], "uncertain_items": ["产品事实证据不足"]}
        current = [
            self._capability(name, current_evidence_id, CURRENT_QUOTE)
            for name in (
                "用户登录",
                "项目看板",
                "文档上传",
                "资料解析",
                "文档草稿生成",
                "DOCX 导出",
            )
        ]
        planned = []
        if multi_tenant_id:
            planned.append(
                self._capability(
                    "多租户协作",
                    multi_tenant_id,
                    PLANNED_MULTI_TENANT_QUOTE,
                    status=ImplementationStatus.PLANNED,
                )
            )
        if comment_id:
            planned.append(
                self._capability(
                    "在线评论",
                    comment_id,
                    PLANNED_COMMENT_QUOTE,
                    status=ImplementationStatus.PLANNED,
                )
            )
        if screenshot_auto_id:
            planned.append(
                self._capability(
                    "截图自动识别",
                    screenshot_auto_id,
                    PLANNED_SCREENSHOT_QUOTE,
                    status=ImplementationStatus.PLANNED,
                )
            )
        return {
            "capabilities": [*current, *planned],
            "business_objects": [],
            "target_users": [],
            "pages": [],
            "workflows": [],
            "uncertain_items": [],
        }

    @staticmethod
    def _evidence_id_for_quote(
        packets: list[dict[str, Any]],
        quote: str,
    ) -> str | None:
        for packet in packets:
            text = f"{packet.get('summary', '')}\n{packet.get('text_excerpt', '')}"
            if quote in text:
                return str(packet["evidence_id"])
        return None

    @staticmethod
    def _capability(
        name: str,
        evidence_id: str,
        quote: str,
        status: ImplementationStatus = ImplementationStatus.CURRENT,
    ) -> dict[str, Any]:
        return {
            "name": name,
            "description": f"{name}能力",
            "capability_type": "web_saas",
            "implementation_status": status.value,
            "supporting_evidence_ids": [evidence_id],
            "supporting_quotes": [quote],
            "confidence": 0.9,
            "reasoning": "基于样例产品资料中的明确描述",
        }

    @staticmethod
    def _accept_candidates(candidates: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "results": [
                {
                    "candidate_index": candidate.get("candidate_index", index),
                    "supported": True,
                    "name_supported": True,
                    "capability_type_supported": True,
                    "implementation_status_supported": True,
                    "corrected_capability_type": None,
                    "corrected_implementation_status": None,
                    "reason": "sample quote supports candidate",
                }
                for index, candidate in enumerate(candidates)
            ]
        }

    @staticmethod
    def _accept_entities(entities: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "results": [
                {
                    "entity_index": entity.get("entity_index", index),
                    "supported": True,
                    "name_supported": True,
                    "entity_type_supported": True,
                    "implementation_status_supported": True,
                    "corrected_implementation_status": None,
                    "reason": "sample quote supports entity",
                }
                for index, entity in enumerate(entities)
            ]
        }

    @staticmethod
    def _section_draft(payload: dict[str, Any]) -> dict[str, Any]:
        section = payload["section_plan"]
        evidence = payload["evidence_bundle"][0]
        title = section["section_title"]
        content = (
            f"{title}章节围绕墨衡演示数据管理平台的当前可用能力展开，"
            "说明用户可见入口、处理流程和生成结果，内容仅依据已确认产品资料组织。"
        )
        return {
            "section_id": section["section_id"],
            "content": content,
            "evidence_ids_used": [evidence["evidence_id"]],
            "citations": [
                {
                    "evidence_id": evidence["evidence_id"],
                    "quote": evidence["quote"],
                }
            ],
            "warnings": [],
        }


def _services(store: StateStore) -> WorkflowServiceRegistry:
    provider = Sprint15SampleProvider()
    safety = PassingWritingPlanSafetyVerifier()
    return WorkflowServiceRegistry(
        source_parsing_service=SourceParsingService(data_dir=store.data_dir),
        evidence_service=EvidenceExtractorService(data_dir=store.data_dir),
        understanding_pipeline_service=UnderstandingPipelineService(
            reference_style_agent=ReferenceStyleAgent(store, llm_provider=provider),
            product_understanding_agent=ProductUnderstandingAgent(
                store,
                llm_provider=provider,
            ),
            software_diagnosis_agent=SoftwareDiagnosisAgent(store),
            template_strategy_agent=TemplateStrategyAgent(store),
            require_reference_style=True,
            require_product_evidence=True,
            require_current_capabilities=True,
        ),
        human_confirm_gate=HumanConfirmGate(store),
        frozen_doc_plan_service=FrozenDocPlanService(store),
        outline_agent=OutlineAgent(store, writing_plan_safety_verifier=safety),
        plan_quality_gate=PlanQualityGate(store, writing_plan_safety_verifier=safety),
        writer_agent=WriterAgentForE2E(store, provider),
        figure_slot_planner=FigureSlotPlannerService(store),
        audit_agent=AuditAgentService(store, llm_provider=provider),
        revision_loop_service=RevisionLoopService(store, llm_provider=provider),
        docx_export_service=DocxExportService(store),
    )


class WriterAgentForE2E:
    def __init__(self, store: StateStore, provider: Sprint15SampleProvider) -> None:
        from docforge_core.agents.writer_agent import WriterAgent

        self._agent = WriterAgent(store, llm_provider=provider)

    def write_v1_draft(self, run_id: str) -> DocForgeState:
        return self._agent.write_v1_draft(run_id)


def _orchestrator(store: StateStore) -> WorkflowOrchestratorService:
    return WorkflowOrchestratorService(store, _services(store))


def _new_sample_run(tmp_path: Path) -> tuple[StateStore, str]:
    store = StateStore(data_dir=tmp_path)
    state = store.create_initial_state()
    load_e2e_sample_project(store, state.run_id)
    return store, state.run_id


def _confirm_minimal_chapters(
    store: StateStore,
    orchestrator: WorkflowOrchestratorService,
    run_id: str,
) -> None:
    state = store.load_state(run_id)
    gate = HumanConfirmGate(store)
    decision = gate.build_default_decision(state)
    assert state.template_strategy is not None
    decision.selected_top_level_chapters = [
        chapter
        for chapter in ("软件概述", "核心功能说明", "用户操作流程")
        if chapter in state.template_strategy.recommended_chapters
    ]
    decision.risk_acknowledged = bool(state.template_strategy.risk_chapters)
    decision.acknowledged_risk_chapters = list(state.template_strategy.risk_chapters)
    summary = orchestrator.submit_human_confirmation(run_id, decision)
    assert summary.success is True
    assert summary.workflow_status == WorkflowStatus.PLAN_FROZEN.value


def _run_sample_to_terminal(tmp_path: Path) -> tuple[StateStore, str, Path]:
    store, run_id = _new_sample_run(tmp_path)
    orchestrator = _orchestrator(store)

    summary = orchestrator.run_until_human_confirmation_required(run_id)
    assert summary.success is True
    assert summary.waiting_for_human_confirmation is True
    _confirm_minimal_chapters(store, orchestrator, run_id)
    summary = orchestrator.run_until_terminal(run_id)

    assert summary.success is True
    assert summary.terminal is True
    state = store.load_state(run_id)
    assert state.workflow_status == WorkflowStatus.FINAL_EXPORTED
    assert state.export_result is not None
    docx_path = get_run_dir(run_id, store.data_dir) / str(state.export_result.docx_path)
    assert docx_path.exists()
    return store, run_id, docx_path


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _draft_sections(draft: dict[str, Any]) -> list[dict[str, Any]]:
    sections: list[dict[str, Any]] = []
    for chapter in draft.get("chapters", []):
        if not isinstance(chapter, dict):
            continue
        for section in chapter.get("sections", []):
            if isinstance(section, dict):
                sections.append(section)
    return sections


def _docx_text(path: Path) -> str:
    document = Document(path)
    return "\n".join(paragraph.text for paragraph in document.paragraphs)


def test_upload_level_e2e_reaches_human_confirmation_before_freezing(
    tmp_path: Path,
) -> None:
    store, run_id = _new_sample_run(tmp_path)
    orchestrator = _orchestrator(store)

    summary = orchestrator.run_until_human_confirmation_required(run_id)

    state = store.load_state(run_id)
    assert summary.waiting_for_human_confirmation is True
    assert state.workflow_status == WorkflowStatus.USER_CONFIRM_REQUIRED
    assert state.next_action == NextAction.ASK_HUMAN_CONFIRMATION
    assert state.frozen_doc_plan is None
    _confirm_minimal_chapters(store, orchestrator, run_id)
    assert store.load_state(run_id).frozen_doc_plan is not None


def test_upload_level_e2e_sample_runs_to_docx(tmp_path: Path) -> None:
    store, run_id, docx_path = _run_sample_to_terminal(tmp_path)
    state = store.load_state(run_id)

    assert state.current_draft_version == "v1"
    assert (get_run_dir(run_id, store.data_dir) / "drafts" / "draft_v1.json").exists()
    assert (get_run_dir(run_id, store.data_dir) / "drafts" / "figure_slots_v1.json").exists()
    assert (get_run_dir(run_id, store.data_dir) / "drafts" / "audit_report_v1.json").exists()
    assert (get_run_dir(run_id, store.data_dir) / "drafts" / "quality_gate_report_v1.json").exists()
    assert Document(docx_path).paragraphs
    text = _docx_text(docx_path)
    assert "软件著作权文档" in text
    assert "墨衡演示数据管理平台" in text
    assert "V1.0" in text
    assert "核心功能说明" in text
    assert "此处建议插入" in text
    assert docx_has_embedded_media(docx_path) is False


def test_upload_level_e2e_validates_final_artifact_lineage(tmp_path: Path) -> None:
    store, run_id, docx_path = _run_sample_to_terminal(tmp_path)
    run_dir = get_run_dir(run_id, store.data_dir)
    draft_path = run_dir / "drafts" / "draft_v1.json"
    figure_path = run_dir / "drafts" / "figure_slots_v1.json"
    audit_path = run_dir / "drafts" / "audit_report_v1.json"
    gate_path = run_dir / "drafts" / "quality_gate_report_v1.json"
    manifest_path = run_dir / "exports" / "export_manifest.json"

    audit = _load_json(audit_path)
    gate = _load_json(gate_path)
    manifest = _load_json(manifest_path)
    assert audit["source_draft_hash"] == _sha256(draft_path)
    assert audit["source_figure_slots_hash"] == _sha256(figure_path)
    assert gate["source_audit_report_hash"] == _sha256(audit_path)
    assert gate["source_draft_hash"] == audit["source_draft_hash"]
    assert gate["source_figure_slots_hash"] == audit["source_figure_slots_hash"]
    assert manifest["output_docx_hash"] == _sha256(docx_path)
    assert manifest["source_quality_gate_report_hash"] == _sha256(gate_path)


def test_upload_level_e2e_final_docx_has_no_internal_artifacts(tmp_path: Path) -> None:
    _store, _run_id, docx_path = _run_sample_to_terminal(tmp_path)
    text = _docx_text(docx_path)

    for token in (
        "evidence_id",
        "source_id",
        "ev_",
        "finding_id",
        "export_manifest",
        "audit_report",
        "quality_gate_report",
        "source_draft_hash",
        CURRENT_QUOTE,
    ):
        assert token not in text


def test_upload_level_e2e_screenshot_is_registered_but_not_ocr(tmp_path: Path) -> None:
    store, run_id, _docx_path = _run_sample_to_terminal(tmp_path)
    state = store.load_state(run_id)
    screenshots = [
        item for item in state.evidence_map if item.evidence_type == EvidenceType.PRODUCT_SCREENSHOT
    ]

    assert len(screenshots) == 2
    assert all(item.screenshot_id for item in screenshots)
    assert all("OCR" in str(item.notes) or "视觉" in str(item.summary) for item in screenshots)
    assert all(item.content_ref and item.content_ref.endswith(".png") for item in screenshots)
    assert all(
        support.evidence_id not in {item.evidence_id for item in screenshots}
        for capability in state.product_capabilities
        for support in capability.evidence_supports
    )
    assert all(
        item.extracted_text_ref is None
        for item in state.parsed_assets
        if item.source_id in state.screenshot_source_ids
    )


def test_upload_level_e2e_screenshot_not_in_frozen_doc_plan_allowed_product_evidence(
    tmp_path: Path,
) -> None:
    store, run_id, _docx_path = _run_sample_to_terminal(tmp_path)
    state = store.load_state(run_id)
    assert state.frozen_doc_plan is not None
    screenshot_ids = {
        item.evidence_id
        for item in state.evidence_map
        if item.evidence_type == EvidenceType.PRODUCT_SCREENSHOT
    }
    policy = state.frozen_doc_plan.evidence_policy
    screenshot_policy = state.frozen_doc_plan.screenshot_policy

    assert screenshot_ids
    assert not screenshot_ids.intersection(policy["allowed_product_evidence_ids"])
    assert screenshot_ids.issubset(set(screenshot_policy["screenshot_evidence_ids"]))
    assert screenshot_policy["visual_parse_status"] == "not_performed"
    assert screenshot_policy["can_use_screenshot_as_strong_evidence"] is False
    assert screenshot_policy["can_use_screenshot_as_product_fact"] is False
    assert screenshot_policy["screenshot_usage"] == "figure_placeholder_only"
    assert screenshot_policy["screenshot_binding_status"] == "not_performed"
    assert all(
        support.evidence_id not in screenshot_ids
        for capability in state.product_capabilities
        for support in capability.evidence_supports
    )
    assert all(
        item["evidence_id"] not in screenshot_ids
        for item in policy["evidence_trace"]
    )
    assert all(
        not screenshot_ids.intersection(fact.get("supporting_evidence_ids", []))
        for fact in state.frozen_doc_plan.feature_policy["current_facts"]
    )


def test_upload_level_e2e_screenshot_not_in_section_required_evidence(
    tmp_path: Path,
) -> None:
    store, run_id, _docx_path = _run_sample_to_terminal(tmp_path)
    state = store.load_state(run_id)
    screenshot_ids = {
        item.evidence_id
        for item in state.evidence_map
        if item.evidence_type == EvidenceType.PRODUCT_SCREENSHOT
    }
    run_dir = get_run_dir(run_id, store.data_dir)
    draft_refs = [item.content_ref for item in state.draft_versions]

    assert screenshot_ids
    assert all(
        not screenshot_ids.intersection(section.required_evidence_ids)
        for section in state.section_plan
    )
    for draft_ref in draft_refs:
        draft = _load_json(run_dir / draft_ref)
        for section in _draft_sections(draft):
            assert not screenshot_ids.intersection(section.get("evidence_ids_used", []))
            citations = section.get("citations", [])
            assert all(citation.get("evidence_id") not in screenshot_ids for citation in citations)

    figure_slots = _load_json(run_dir / "drafts" / "figure_slots_v1.json")
    figure_text = json.dumps(figure_slots, ensure_ascii=False)
    assert "required_evidence_ids" not in figure_text
    assert all(
        "evidence_id" not in slot and "citations" not in slot
        for slot in figure_slots["figure_slots"]
    )
    assert all(slot["status"] == "missing" for slot in figure_slots["figure_slots"])


def test_upload_level_e2e_rejects_missing_product_evidence(tmp_path: Path) -> None:
    store = StateStore(data_dir=tmp_path)
    state = store.create_initial_state()
    fixture_dir = default_e2e_sample_dir()
    registry = SourceFileRegistry(state.run_id, data_dir=tmp_path)
    reference = registry.register_reference_file(
        "reference_soft_copyright.md",
        (fixture_dir / "reference_soft_copyright.md").read_bytes(),
    )
    store.add_source_item(state.run_id, reference)

    summary = _orchestrator(store).run_until_human_confirmation_required(state.run_id)

    reloaded = store.load_state(state.run_id)
    assert summary.success is False
    assert "product_evidence" in str(summary.error)
    assert reloaded.workflow_status == WorkflowStatus.EVIDENCE_MAPPED
    assert reloaded.template_strategy is None


def test_upload_level_e2e_rejects_missing_reference_style(tmp_path: Path) -> None:
    store = StateStore(data_dir=tmp_path)
    state = store.create_initial_state()
    fixture_dir = default_e2e_sample_dir()
    registry = SourceFileRegistry(state.run_id, data_dir=tmp_path)
    product = registry.register_product_file(
        "product_prd.md",
        (fixture_dir / "product_prd.md").read_bytes(),
        source_type=SourceType.PRD,
    )
    store.add_source_item(state.run_id, product)

    summary = _orchestrator(store).run_until_human_confirmation_required(state.run_id)

    reloaded = store.load_state(state.run_id)
    assert summary.success is False
    assert "reference_style" in str(summary.error)
    assert reloaded.workflow_status == WorkflowStatus.EVIDENCE_MAPPED
    assert reloaded.template_strategy is None


def test_upload_level_e2e_fails_closed_when_reference_used_as_product_evidence(
    tmp_path: Path,
) -> None:
    store = StateStore(data_dir=tmp_path)
    state = store.create_initial_state()
    fixture_dir = default_e2e_sample_dir()
    registry = SourceFileRegistry(state.run_id, data_dir=tmp_path)
    reference = registry.register_reference_file(
        "real_reference.md",
        (fixture_dir / "reference_soft_copyright.md").read_bytes(),
    )
    wrong_product = registry.register_product_file(
        "reference_misregistered.md",
        (fixture_dir / "reference_soft_copyright.md").read_bytes(),
        source_type=SourceType.PRD,
    )
    store.add_source_item(state.run_id, reference)
    store.add_source_item(state.run_id, wrong_product)

    summary = _orchestrator(store).run_until_human_confirmation_required(state.run_id)

    reloaded = store.load_state(state.run_id)
    assert summary.success is False
    assert "validated/current" in str(summary.error)
    assert reloaded.template_strategy is None
    assert reloaded.product_capabilities == []


def test_upload_level_e2e_resume_after_human_confirmation_pause(tmp_path: Path) -> None:
    store, run_id = _new_sample_run(tmp_path)
    first = _orchestrator(store)

    summary = first.run_until_human_confirmation_required(run_id)
    assert summary.waiting_for_human_confirmation is True
    paused = store.load_state(run_id)
    assert paused.workflow_status == WorkflowStatus.USER_CONFIRM_REQUIRED
    assert paused.frozen_doc_plan is None

    resumed = _orchestrator(store)
    _confirm_minimal_chapters(store, resumed, run_id)
    summary = resumed.run_until_terminal(run_id)
    assert summary.terminal is True
    final_state = store.load_state(run_id)
    assert final_state.workflow_status == WorkflowStatus.FINAL_EXPORTED


def test_upload_level_e2e_resume_after_audit_report_created(tmp_path: Path) -> None:
    store, run_id = _new_sample_run(tmp_path)
    orchestrator = _orchestrator(store)
    assert orchestrator.run_until_human_confirmation_required(run_id).waiting_for_human_confirmation
    _confirm_minimal_chapters(store, orchestrator, run_id)
    while store.load_state(run_id).workflow_status != WorkflowStatus.DRAFT_AUDITED:
        summary = orchestrator.run_next_step(run_id)
        assert summary.success is True

    audit_hash = _sha256(get_run_dir(run_id, store.data_dir) / "drafts" / "audit_report_v1.json")
    summary = _orchestrator(store).resume(run_id)

    assert summary.terminal is True
    assert _sha256(get_run_dir(run_id, store.data_dir) / "drafts" / "audit_report_v1.json") == audit_hash
    assert store.load_state(run_id).workflow_status == WorkflowStatus.FINAL_EXPORTED


def test_upload_level_e2e_repeated_continue_does_not_duplicate_artifacts(
    tmp_path: Path,
) -> None:
    store, run_id, _docx_path = _run_sample_to_terminal(tmp_path)
    state_before = store.load_state(run_id)
    run_dir = get_run_dir(run_id, store.data_dir)
    draft_files_before = sorted(path.name for path in (run_dir / "drafts").glob("draft_v*.json"))

    summary = _orchestrator(store).run_until_terminal(run_id)

    state_after = store.load_state(run_id)
    draft_files_after = sorted(path.name for path in (run_dir / "drafts").glob("draft_v*.json"))
    assert summary.terminal is True
    assert state_after.workflow_status == WorkflowStatus.FINAL_EXPORTED
    assert len(state_after.draft_versions) == len(state_before.draft_versions)
    assert draft_files_after == draft_files_before
    assert state_after.export_result == state_before.export_result


@pytest.mark.parametrize("source_name", ["login_page.png", "dashboard_page.png"])
def test_upload_level_sample_screenshot_sources_parse_without_text(
    tmp_path: Path,
    source_name: str,
) -> None:
    store, run_id = _new_sample_run(tmp_path)
    SourceParsingService(data_dir=tmp_path).parse_run(run_id)
    state = store.load_state(run_id)
    source = next(item for item in state.source_registry if item.file_name == source_name)
    asset = next(item for item in state.parsed_assets if item.source_id == source.source_id)

    assert source.parse_status == ParseStatus.PARSED
    assert asset.extracted_text_ref is None
    assert asset.image_ref is not None
