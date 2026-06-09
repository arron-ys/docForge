"""Understanding and diagnosis agents."""

from .audit_agent import AuditAgentService
from .capability_grounding_verifier import ProductCapabilityGroundingVerifier
from .capability_validation_trace import (
    build_capability_claim_hash,
    build_capability_validation_trace,
    build_evidence_supports_hash,
    validate_capability_trace,
)
from .figure_slot_planner import FigureSlotPlannerService, FigureSlotValidator
from .frozen_doc_plan_service import FrozenDocPlanService
from .human_confirm_gate import HumanConfirmGate
from .human_confirm_pipeline_service import HumanConfirmPipelineService
from .outline_agent import OutlineAgent
from .outline_traversal import OutlineSectionNode, iter_outline_sections
from .outline_validator import OutlineValidator
from .product_understanding_agent import ProductUnderstandingAgent
from .profile_entity_grounding_verifier import ProductProfileEntityGroundingVerifier
from .reference_style_agent import ReferenceStyleAgent
from .revision_agent import (
    DraftRevisionAgent,
    RevisedDraftValidator,
    RevisionInstructionBuilder,
)
from .revision_loop_service import RevisionLoopService
from .section_draft_safety_verifier import SectionDraftSafetyVerifier
from .section_draft_validator import SectionDraftValidator
from .section_evidence_policy import is_capability_related_section
from .section_plan_validator import SectionPlanValidator
from .software_diagnosis_agent import SoftwareDiagnosisAgent
from .template_strategy_agent import TemplateStrategyAgent
from .title_injection_safety import validate_outline_title_safe
from .understanding_pipeline_service import UnderstandingPipelineService
from .writer_agent import WriterAgent
from .writing_goal_safety import validate_writing_goal_safe
from .writing_plan_safety_items import (
    collect_writing_plan_safety_items_from_outline,
    collect_writing_plan_safety_items_from_section_plan,
)
from .writing_plan_safety_verifier import (
    WritingPlanSafetyVerifier,
    WritingPlanSafetyVerifierProtocol,
)

__all__ = [
    "ProductCapabilityGroundingVerifier",
    "AuditAgentService",
    "build_capability_claim_hash",
    "build_capability_validation_trace",
    "build_evidence_supports_hash",
    "validate_capability_trace",
    "FrozenDocPlanService",
    "FigureSlotPlannerService",
    "FigureSlotValidator",
    "HumanConfirmGate",
    "HumanConfirmPipelineService",
    "OutlineAgent",
    "OutlineSectionNode",
    "OutlineValidator",
    "iter_outline_sections",
    "is_capability_related_section",
    "SectionDraftSafetyVerifier",
    "SectionDraftValidator",
    "SectionPlanValidator",
    "ProductProfileEntityGroundingVerifier",
    "ProductUnderstandingAgent",
    "ReferenceStyleAgent",
    "DraftRevisionAgent",
    "RevisedDraftValidator",
    "RevisionInstructionBuilder",
    "RevisionLoopService",
    "SoftwareDiagnosisAgent",
    "TemplateStrategyAgent",
    "validate_outline_title_safe",
    "UnderstandingPipelineService",
    "validate_writing_goal_safe",
    "WriterAgent",
    "collect_writing_plan_safety_items_from_outline",
    "collect_writing_plan_safety_items_from_section_plan",
    "WritingPlanSafetyVerifier",
    "WritingPlanSafetyVerifierProtocol",
]
