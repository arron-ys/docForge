"""Shared workflow service wiring for all local DocForge entrypoints."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

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
from docforge_core.agents.writer_agent import WriterAgent
from docforge_core.evidence.extractor import EvidenceExtractorService
from docforge_core.exporters.docx_exporter import DocxExportService
from docforge_core.gates.plan_quality_gate import PlanQualityGate
from docforge_core.io.state_store import StateStore
from docforge_core.llm.provider_factory import create_llm_provider
from docforge_core.parsers.source_parsing_service import SourceParsingService

from .orchestrator import WorkflowOrchestratorService, WorkflowServiceRegistry


class LazyWorkflowService:
    """Instantiate LLM-backed services only when the workflow reaches that step."""

    def __init__(self, factory: Callable[[], Any]) -> None:
        self._factory = factory
        self._service: Any | None = None

    def _get(self) -> Any:
        if self._service is None:
            self._service = self._factory()
        return self._service


class LazyUnderstandingPipelineService(LazyWorkflowService):
    def run_until_template_recommended(self, run_id: str):
        return self._get().run_until_template_recommended(run_id)


class LazyOutlineAgent(LazyWorkflowService):
    def create_outline(self, run_id: str):
        return self._get().create_outline(run_id)


class LazyPlanQualityGate(LazyWorkflowService):
    def run(self, run_id: str):
        return self._get().run(run_id)


class LazyWriterAgent(LazyWorkflowService):
    def write_v1_draft(self, run_id: str):
        return self._get().write_v1_draft(run_id)


class LazyAuditAgent(LazyWorkflowService):
    def audit_draft(self, run_id: str):
        return self._get().audit_draft(run_id)


class LazyRevisionLoopService(LazyWorkflowService):
    def run_quality_gate_for_current_draft(self, run_id: str):
        return self._get().run_quality_gate_for_current_draft(run_id)

    def revise_current_draft(self, run_id: str):
        return self._get().revise_current_draft(run_id)

    def audit_revised_draft(self, run_id: str):
        return self._get().audit_revised_draft(run_id)


def build_workflow_service_registry(state_store: StateStore) -> WorkflowServiceRegistry:
    """Build the complete service registry used by Streamlit and FastAPI."""
    return WorkflowServiceRegistry(
        source_parsing_service=SourceParsingService(data_dir=state_store.data_dir),
        evidence_service=EvidenceExtractorService(data_dir=state_store.data_dir),
        understanding_pipeline_service=LazyUnderstandingPipelineService(
            lambda: _create_understanding_pipeline(state_store)
        ),
        human_confirm_gate=HumanConfirmGate(state_store),
        frozen_doc_plan_service=FrozenDocPlanService(state_store),
        outline_agent=LazyOutlineAgent(
            lambda: OutlineAgent(state_store, llm_provider=create_llm_provider())
        ),
        plan_quality_gate=LazyPlanQualityGate(
            lambda: PlanQualityGate(state_store, llm_provider=create_llm_provider())
        ),
        writer_agent=LazyWriterAgent(
            lambda: WriterAgent(state_store, llm_provider=create_llm_provider())
        ),
        figure_slot_planner=FigureSlotPlannerService(state_store),
        audit_agent=LazyAuditAgent(
            lambda: AuditAgentService(state_store, llm_provider=create_llm_provider())
        ),
        revision_loop_service=LazyRevisionLoopService(
            lambda: RevisionLoopService(state_store, llm_provider=create_llm_provider())
        ),
        docx_export_service=DocxExportService(state_store),
    )


def build_workflow_orchestrator(state_store: StateStore) -> WorkflowOrchestratorService:
    """Build a workflow orchestrator with all local services wired."""
    return WorkflowOrchestratorService(
        state_store=state_store,
        services=build_workflow_service_registry(state_store),
    )


def _create_understanding_pipeline(
    state_store: StateStore,
) -> UnderstandingPipelineService:
    llm_provider = create_llm_provider()
    return UnderstandingPipelineService(
        reference_style_agent=ReferenceStyleAgent(
            state_store,
            llm_provider=llm_provider,
        ),
        product_understanding_agent=ProductUnderstandingAgent(
            state_store,
            llm_provider=llm_provider,
        ),
        software_diagnosis_agent=SoftwareDiagnosisAgent(
            state_store,
            llm_provider=llm_provider,
        ),
        template_strategy_agent=TemplateStrategyAgent(
            state_store,
            llm_provider=llm_provider,
        ),
        require_reference_style=False,
        require_product_evidence=True,
        require_current_capabilities=True,
    )
