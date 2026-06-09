"""领域枚举定义。所有枚举值与设计文档 DocForgeState v2.0 / WF-02 保持一致。"""

from enum import StrEnum


class WorkflowStatus(StrEnum):
    """工作流状态机节点，对应 WF-02 主流程各阶段。"""

    CREATED = "CREATED"
    MATERIAL_UPLOADED = "MATERIAL_UPLOADED"
    SOURCE_PARSED = "SOURCE_PARSED"
    REFERENCE_STYLE_ANALYZED = "REFERENCE_STYLE_ANALYZED"
    PRODUCT_UNDERSTOOD = "PRODUCT_UNDERSTOOD"
    EVIDENCE_MAPPED = "EVIDENCE_MAPPED"
    DIAGNOSED = "DIAGNOSED"
    TEMPLATE_RECOMMENDED = "TEMPLATE_RECOMMENDED"
    USER_CONFIRM_REQUIRED = "USER_CONFIRM_REQUIRED"
    USER_CONFIRMED = "USER_CONFIRMED"
    PLAN_FROZEN = "PLAN_FROZEN"
    OUTLINE_CREATED = "OUTLINE_CREATED"
    PLAN_GATE_REVIEWING = "PLAN_GATE_REVIEWING"
    PLAN_GATE_PASSED = "PLAN_GATE_PASSED"
    PLAN_GATE_FAILED = "PLAN_GATE_FAILED"
    DRAFT_V1_CREATED = "DRAFT_V1_CREATED"
    FIGURE_SLOTS_PLANNED = "FIGURE_SLOTS_PLANNED"
    DRAFT_AUDITED = "DRAFT_AUDITED"
    DRAFT_QUALITY_GATE_PASSED = "DRAFT_QUALITY_GATE_PASSED"
    DRAFT_REVISION_REQUIRED = "DRAFT_REVISION_REQUIRED"
    AUDIT_V1_COMPLETED = "AUDIT_V1_COMPLETED"
    DRAFT_V2_CREATED = "DRAFT_V2_CREATED"
    DRAFT_V2_AUDITED = "DRAFT_V2_AUDITED"
    AUDIT_V2_COMPLETED = "AUDIT_V2_COMPLETED"
    DRAFT_V3_CREATED = "DRAFT_V3_CREATED"
    DRAFT_V3_AUDITED = "DRAFT_V3_AUDITED"
    AUDIT_V3_COMPLETED = "AUDIT_V3_COMPLETED"
    RISK_VERSION_READY = "RISK_VERSION_READY"
    DRAFT_GATE_PASSED = "DRAFT_GATE_PASSED"
    REVISION_REQUIRED = "REVISION_REQUIRED"
    FINAL_EXPORTED = "FINAL_EXPORTED"
    RISK_EXPORTED = "RISK_EXPORTED"
    FAILED = "FAILED"


class NextAction(StrEnum):
    """下一步动作指针，由 OrchestratorAgent 写入，路由器读取。"""

    INGEST_MATERIALS = "ingest_materials"
    PARSE_SOURCES = "parse_sources"
    ANALYZE_REFERENCE_STYLE = "analyze_reference_style"
    UNDERSTAND_PRODUCT = "understand_product"
    EXTRACT_EVIDENCE = "extract_evidence"
    DIAGNOSE_SOFTWARE_TYPE = "diagnose_software_type"
    RECOMMEND_TEMPLATE = "recommend_template"
    ASK_HUMAN_CONFIRMATION = "ask_human_confirmation"
    FREEZE_DOC_PLAN = "freeze_doc_plan"
    CREATE_OUTLINE = "create_outline"
    RUN_PLAN_QUALITY_GATE = "run_plan_quality_gate"
    ASK_MISSING_INFORMATION = "ask_missing_information"
    WRITE_DRAFT = "write_draft"
    PLAN_FIGURE_SLOTS = "plan_figure_slots"
    BIND_SCREENSHOTS = "bind_screenshots"
    AUDIT_DRAFT = "audit_draft"
    RUN_DRAFT_QUALITY_GATE = "run_draft_quality_gate"
    REVISE_DRAFT = "revise_draft"
    AUDIT_REVISED_DRAFT = "audit_revised_draft"
    EXPORT_DOCX = "export_docx"
    EXPORT_RISK_DOCX = "export_risk_docx"
    EXPORT_FINAL_DOC = "export_final_doc"
    EXPORT_RISK_DOC = "export_risk_doc"
    STOP = "stop"


class SourceType(StrEnum):
    """
    业务来源类型：说明这份资料在业务上是什么角色。

    注意：docx / pdf / png / jpg 等文件格式不属于来源类型，
    只能填入 FileType，不得填入此字段。
    """

    REFERENCE_SOFT_COPYRIGHT_DOC = "reference_soft_copyright_doc"
    PRODUCT_INTRO_DOC = "product_intro_doc"
    PRD = "prd"
    HLD = "hld"
    DETAILED_DESIGN_DOC = "detailed_design_doc"
    SCREENSHOT = "screenshot"
    USER_NOTE = "user_note"
    # Phase 2 预留 — MVP 阶段允许模型存在，但不得在默认流程中创建
    PRODUCT_URL = "product_url"
    OTHER = "other"


class FileType(StrEnum):
    """
    文件格式类型：说明这份资料的实际文件格式是什么。

    注意：docx / pdf / png / jpg 等格式只能填入此字段，
    不得混入 SourceType。
    """

    DOCX = "docx"
    PDF = "pdf"
    MD = "md"
    TXT = "txt"
    HTML = "html"
    PNG = "png"
    JPG = "jpg"
    JPEG = "jpeg"
    WEBP = "webp"
    NONE = "none"
    OTHER = "other"


class AssetType(StrEnum):
    """解析资产类型。url_page 为 Phase 2 预留。"""

    TEXT = "text"
    IMAGE = "image"
    TABLE = "table"
    PAGE = "page"
    URL_PAGE = "url_page"
    SCREENSHOT = "screenshot"
    METADATA = "metadata"


class CorpusType(StrEnum):
    """
    证据语料类型，是证据隔离的生命线。

    - reference_style  : 外部参考软著，只允许学写法，禁止提供产品事实
    - product_evidence : 自有产品资料，可作为产品事实依据
    """

    REFERENCE_STYLE = "reference_style"
    PRODUCT_EVIDENCE = "product_evidence"


class AllowedUsage(StrEnum):
    """
    允许用途，是证据能否进入事实链路的核心边界：

    - style_only: 仅用于参考写法、目录结构、章法和语言风格。
    - factual_evidence: 可作为产品事实来源。
    - display_material_only: 仅作为展示素材、配图候选、占位材料登记；
      不得作为产品事实来源，不得进入 WriterAgent 的事实引用链，
      不得被 ProductUnderstandingAgent 当作产品能力证据。
    """

    STYLE_ONLY = "style_only"
    FACTUAL_EVIDENCE = "factual_evidence"
    DISPLAY_MATERIAL_ONLY = "display_material_only"


class ParseStatus(StrEnum):
    """文件解析状态。"""

    PENDING = "pending"
    PARSED = "parsed"
    FAILED = "failed"
    SKIPPED = "skipped"


class EvidenceType(StrEnum):
    """证据单元类型。product_url_page 为 Phase 2 预留。"""

    PRODUCT_DOCUMENT = "product_document"
    PRODUCT_SCREENSHOT = "product_screenshot"
    USER_CONFIRMATION = "user_confirmation"
    REFERENCE_STYLE_ONLY = "reference_style_only"
    PRODUCT_URL_PAGE = "product_url_page"  # Phase 2 预留，MVP 不使用


class EvidenceStrength(StrEnum):
    """证据强度分级。"""

    STRONG = "strong"
    MEDIUM = "medium"
    WEAK = "weak"
    NOT_ALLOWED_AS_FACT = "not_allowed_as_fact"


class ProductFactType(StrEnum):
    """产品事实类型。"""

    SOFTWARE_NAME = "software_name"
    VERSION = "version"
    MODULE = "module"
    FEATURE = "feature"
    WORKFLOW = "workflow"
    PAGE = "page"
    TECHNICAL_ENVIRONMENT = "technical_environment"
    PERMISSION = "permission"
    DATA_OBJECT = "data_object"
    OTHER = "other"


class ImplementationStatus(StrEnum):
    """产品能力在当前版本中的实现状态。"""

    CURRENT = "current"
    PLANNED = "planned"
    UNKNOWN = "unknown"


class ValidationStatus(StrEnum):
    """产品能力的证据校验状态。"""

    VALIDATED = "validated"
    UNSUPPORTED = "unsupported"
    NEEDS_CONFIRMATION = "needs_confirmation"


class CapabilityType(StrEnum):
    """由 LLM 语义选择、并经证据引用校验的产品能力分类。"""

    WEB_SAAS = "web_saas"
    DATA_MANAGEMENT = "data_management"
    DATASET_MANAGEMENT = "dataset_management"
    DATA_QUALITY = "data_quality"
    ANNOTATION = "annotation"
    AI_TRAINING = "ai_training"
    AI_INFERENCE = "ai_inference"
    AI_EVALUATION = "ai_evaluation"
    MODEL_ASSET_MANAGEMENT = "model_asset_management"
    PERMISSION_MANAGEMENT = "permission_management"
    USER_MANAGEMENT = "user_management"
    FILE_IMPORT_EXPORT = "file_import_export"
    SIMULATION_MANAGEMENT = "simulation_management"
    THREE_D_MODEL_MANAGEMENT = "three_d_model_management"
    CAD_MODEL_MANAGEMENT = "cad_model_management"
    AUTOMOTIVE_DOMAIN = "automotive_domain"
    SYSTEM_ADMINISTRATION = "system_administration"
    OTHER = "other"


class ConfirmationStatus(StrEnum):
    """用户确认状态。"""

    PENDING = "pending"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    OVERRIDDEN = "overridden"


class ConfirmationType(StrEnum):
    """用户确认类型。"""

    TEMPLATE_STRATEGY = "template_strategy"
    MISSING_INFORMATION = "missing_information"
    FEATURE_CONFIRMATION = "feature_confirmation"
    SCREENSHOT_PERMISSION = "screenshot_permission"
    FINAL_EXPORT = "final_export"


class LockedStatus(StrEnum):
    """FrozenDocPlan 锁定状态。"""

    DRAFT = "draft"
    LOCKED = "locked"
    UNLOCKED_FOR_REVISION = "unlocked_for_revision"


class LockedBy(StrEnum):
    """FrozenDocPlan 锁定来源。"""

    ORCHESTRATOR = "orchestrator"
    HUMAN = "human"
    SYSTEM = "system"


class AuditSeverity(StrEnum):
    """审计问题严重级别。Blocker 具有一票否决权。"""

    BLOCKER = "blocker"
    MAJOR = "major"
    MINOR = "minor"
    SUGGESTION = "suggestion"


class AuditIssueType(StrEnum):
    """审计问题分类。"""

    PLAN_VIOLATION = "plan_violation"
    UNSUPPORTED_FEATURE = "unsupported_feature"
    FUTURE_AS_CURRENT = "future_as_current"
    REFERENCE_CONTAMINATION = "reference_contamination"
    SCREENSHOT_MISMATCH = "screenshot_mismatch"
    VERSION_INCONSISTENCY = "version_inconsistency"
    MISSING_ENVIRONMENT = "missing_environment"
    WEAK_OPERATION_STEPS = "weak_operation_steps"
    ADVERTISING_LANGUAGE = "advertising_language"
    LEGAL_RISK = "legal_risk"
    OTHER = "other"


class AuditCategory(StrEnum):
    """Sprint 11 structured draft-audit finding categories."""

    DRAFT_SCHEMA_INVALID = "draft_schema_invalid"
    PLAN_VIOLATION = "plan_violation"
    SECTION_MISSING = "section_missing"
    SECTION_NOT_IN_PLAN = "section_not_in_plan"
    SECTION_METADATA_MISMATCH = "section_metadata_mismatch"
    EVIDENCE_ID_NOT_FOUND = "evidence_id_not_found"
    EVIDENCE_ID_OUT_OF_SECTION_PLAN = "evidence_id_out_of_section_plan"
    CITATION_OUT_OF_SECTION_PLAN = "citation_out_of_section_plan"
    CITATION_QUOTE_NOT_FOUND = "citation_quote_not_found"
    REFERENCE_STYLE_USED_AS_FACT = "reference_style_used_as_fact"
    NON_FACTUAL_EVIDENCE_USED_AS_FACT = "non_factual_evidence_used_as_fact"
    FIGURE_SLOT_CLAIMS_EXISTING_IMAGE = "figure_slot_claims_existing_image"
    FIGURE_SLOT_SECTION_NOT_FOUND = "figure_slot_section_not_found"
    FIGURE_SLOT_INVALID = "figure_slot_invalid"
    SOFTWARE_IDENTITY_MISMATCH = "software_identity_mismatch"
    SOFTWARE_VERSION_MISMATCH = "software_version_mismatch"
    SOFTWARE_IDENTITY_MISSING = "software_identity_missing"
    CLAIM_NOT_SUPPORTED_BY_QUOTE = "claim_not_supported_by_quote"
    PLANNED_WRITTEN_AS_CURRENT = "planned_written_as_current"
    UNKNOWN_WRITTEN_AS_CURRENT = "unknown_written_as_current"
    UNSUPPORTED_CAPABILITY_CLAIM = "unsupported_capability_claim"
    EXAGGERATED_CLAIM = "exaggerated_claim"
    STYLE_DEVIATION = "style_deviation"
    FIGURE_SLOT_SEMANTIC_MISMATCH = "figure_slot_semantic_mismatch"
    SEMANTIC_VERIFIER_FAILED = "semantic_verifier_failed"


class GateType(StrEnum):
    """质量门禁类型。"""

    PLAN_QUALITY_GATE = "plan_quality_gate"
    DRAFT_QUALITY_GATE = "draft_quality_gate"


class DraftQualityGateDecision(StrEnum):
    """Sprint 12 draft quality-gate decision."""

    REQUIRE_REVISION = "require_revision"
    EXPORT_DOCX = "export_docx"
    RISK_EXPORT_REQUIRED = "risk_export_required"


class ExportType(StrEnum):
    """导出产物类型。"""

    FINAL = "final"
    RISK = "risk"


class ScreenshotBindingStatus(StrEnum):
    """截图绑定状态。"""

    BOUND = "bound"
    MISSING = "missing"
    CANDIDATE = "candidate"
    REJECTED = "rejected"


class MissingInformationStatus(StrEnum):
    """缺失信息处理状态。"""

    PENDING = "pending"
    ANSWERED = "answered"
    IGNORED = "ignored"


class DraftVersionLabel(StrEnum):
    """草稿版本标签。"""

    V1 = "v1"
    V2 = "v2"
    V3 = "v3"
    RISK = "risk"
