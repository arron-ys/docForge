from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

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
from docforge_core.domain.enums import ImplementationStatus, WorkflowStatus
from docforge_core.domain.schemas import DocForgeState
from docforge_core.evidence.extractor import EvidenceExtractorService
from docforge_core.exporters.docx_exporter import DocxExportService
from docforge_core.gates.plan_quality_gate import PlanQualityGate
from docforge_core.io.run_paths import get_run_dir
from docforge_core.io.state_store import StateStore
from docforge_core.llm.base import LLMMessage, LLMProvider, LLMResponse
from docforge_core.parsers.source_parsing_service import SourceParsingService
from docforge_core.workflow import WorkflowOrchestratorService, WorkflowServiceRegistry
from docforge_core.workflow.e2e_sample_runner import load_e2e_sample_project

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
