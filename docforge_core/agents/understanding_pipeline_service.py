"""Sequential Sprint 6 understanding and diagnosis pipeline."""

from docforge_core.domain.enums import (
    AllowedUsage,
    CorpusType,
    EvidenceType,
    ImplementationStatus,
    ValidationStatus,
    WorkflowStatus,
)
from docforge_core.domain.schemas import DocForgeState

from .product_understanding_agent import ProductUnderstandingAgent
from .reference_style_agent import ReferenceStyleAgent
from .software_diagnosis_agent import SoftwareDiagnosisAgent
from .template_strategy_agent import TemplateStrategyAgent


class UnderstandingPipelineService:
    """Run all Sprint 6 agents without entering human confirmation."""

    def __init__(
        self,
        reference_style_agent: ReferenceStyleAgent | None = None,
        product_understanding_agent: ProductUnderstandingAgent | None = None,
        software_diagnosis_agent: SoftwareDiagnosisAgent | None = None,
        template_strategy_agent: TemplateStrategyAgent | None = None,
        require_reference_style: bool = False,
        require_product_evidence: bool = False,
        require_current_capabilities: bool = False,
    ) -> None:
        self.reference_style_agent = reference_style_agent or ReferenceStyleAgent()
        self.product_understanding_agent = product_understanding_agent or ProductUnderstandingAgent()
        self.software_diagnosis_agent = software_diagnosis_agent or SoftwareDiagnosisAgent()
        self.template_strategy_agent = template_strategy_agent or TemplateStrategyAgent()
        self.require_reference_style = require_reference_style
        self.require_product_evidence = require_product_evidence
        self.require_current_capabilities = require_current_capabilities

    def run_until_template_recommended(self, run_id: str) -> DocForgeState:
        state = self.reference_style_agent.state_store.load_state(run_id)
        if state.workflow_status != WorkflowStatus.EVIDENCE_MAPPED:
            raise ValueError("理解与诊断流程要求 workflow_status 为 EVIDENCE_MAPPED")
        self._validate_required_evidence(state)

        self.reference_style_agent.analyze_run(run_id)
        state = self.product_understanding_agent.understand_run(run_id)
        self._validate_required_current_capabilities(state)
        self.software_diagnosis_agent.diagnose_run(run_id)
        return self.template_strategy_agent.recommend_run(run_id)

    def _validate_required_evidence(self, state: DocForgeState) -> None:
        if self.require_reference_style and not any(
            item.corpus_type == CorpusType.REFERENCE_STYLE
            and item.allowed_usage == AllowedUsage.STYLE_ONLY
            for item in state.evidence_map
        ):
            raise ValueError("真实样例流程要求至少上传 reference_style 参考软著资料")
        if self.require_product_evidence and not any(
            item.corpus_type == CorpusType.PRODUCT_EVIDENCE
            and item.allowed_usage == AllowedUsage.FACTUAL_EVIDENCE
            and item.evidence_type != EvidenceType.PRODUCT_SCREENSHOT
            for item in state.evidence_map
        ):
            raise ValueError("真实样例流程要求至少上传非截图 product_evidence 产品资料")

    def _validate_required_current_capabilities(self, state: DocForgeState) -> None:
        if not self.require_current_capabilities:
            return
        if not any(
            item.validation_status == ValidationStatus.VALIDATED
            and item.implementation_status == ImplementationStatus.CURRENT
            for item in state.product_capabilities
        ):
            raise ValueError("真实样例流程要求至少识别一个 validated/current 产品能力")
