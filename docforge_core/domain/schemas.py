"""
领域 Pydantic 模型定义。

设计原则（来自《初版需求描述》）：
1. SourceItem 必须区分 source_type（业务来源类型）和 file_type（文件格式）。
2. corpus_type / allowed_usage 是证据隔离的生命线：
   - reference_style  → style_only
   - product_evidence → factual_evidence 或 display_material_only
3. State 只保存路径、ID、结构化摘要和状态指针，不保存完整文档、截图、DOCX、大段原文。
4. Qdrant collection 名必须是 docforge_{run_id}。
5. URL 相关字段为 Phase 2 预留，MVP 默认为空，不进入工作流。
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .enums import (
    AllowedUsage,
    AssetType,
    AuditCategory,
    AuditIssueType,
    AuditSeverity,
    CapabilityType,
    ConfirmationStatus,
    ConfirmationType,
    CorpusType,
    DraftQualityGateDecision,
    DraftVersionLabel,
    EvidenceStrength,
    EvidenceType,
    ExportType,
    FileType,
    GateType,
    ImplementationStatus,
    LockedBy,
    LockedStatus,
    MissingInformationStatus,
    NextAction,
    ParseStatus,
    ProductFactType,
    ScreenshotBindingStatus,
    SourceType,
    ValidationStatus,
    WorkflowStatus,
)


def _utcnow_iso() -> str:
    return datetime.now(UTC).isoformat()


def _new_id() -> str:
    return uuid4().hex


# ─────────────────────────────────────────────
# 1. SourceItem — 资料登记表中的一条记录
# ─────────────────────────────────────────────


class SourceItem(BaseModel):
    """
    一份上传资料的完整元信息。

    校验规则：
    - corpus_type=reference_style  → allowed_usage 必须是 style_only
    - corpus_type=product_evidence → 文档/确认类事实必须是 factual_evidence，截图必须是 display_material_only
    - source_type=reference_soft_copyright_doc → is_reference_source 必须为 True
    - source_type 不允许填 docx/pdf/png/jpg（这些只能填 file_type）
    - source_type=product_url → Phase 2 预留，MVP 不在默认流程中创建
    """

    source_id: str = Field(default_factory=_new_id)
    source_type: SourceType
    file_type: FileType
    corpus_type: CorpusType
    allowed_usage: AllowedUsage

    file_name: str | None = None
    file_path: str | None = None
    # Phase 2 预留字段，MVP 阶段不使用
    url: str | None = None

    is_reference_source: bool = False
    is_product_source: bool = False
    uploaded_at: str = Field(default_factory=_utcnow_iso)
    parse_status: ParseStatus = ParseStatus.PENDING
    parse_error: str | None = None
    notes: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("source_type", mode="before")
    @classmethod
    def _reject_file_type_as_source_type(cls, value: object) -> object:
        """文件格式只能放在 file_type，不能误填到 source_type。"""
        file_format_values = {
            FileType.DOCX.value,
            FileType.PDF.value,
            FileType.MD.value,
            FileType.TXT.value,
            FileType.HTML.value,
            FileType.PNG.value,
            FileType.JPG.value,
            FileType.JPEG.value,
            FileType.WEBP.value,
        }
        if value in file_format_values:
            raise ValueError(
                "source_type 必须是业务来源类型，docx/pdf/png/jpg 等文件格式只能填入 file_type"
            )
        return value

    @model_validator(mode="after")
    def _validate_source_isolation(self) -> SourceItem:
        if (
            self.corpus_type == CorpusType.REFERENCE_STYLE
            and self.allowed_usage != AllowedUsage.STYLE_ONLY
        ):
            raise ValueError(
                "corpus_type=reference_style 时，allowed_usage 必须是 style_only，"
                f"实际收到: {self.allowed_usage}"
            )
        if self.corpus_type == CorpusType.REFERENCE_STYLE and not self.is_reference_source:
            raise ValueError("corpus_type=reference_style 时，is_reference_source 必须为 True")
        if self.corpus_type == CorpusType.REFERENCE_STYLE and self.is_product_source:
            raise ValueError("corpus_type=reference_style 时，is_product_source 必须为 False")

        if self.corpus_type == CorpusType.PRODUCT_EVIDENCE:
            expected_usage = (
                AllowedUsage.DISPLAY_MATERIAL_ONLY
                if self.source_type == SourceType.SCREENSHOT
                else AllowedUsage.FACTUAL_EVIDENCE
            )
        else:
            expected_usage = None
        if (
            self.corpus_type == CorpusType.PRODUCT_EVIDENCE
            and expected_usage is not None
            and self.allowed_usage != expected_usage
        ):
            raise ValueError(
                "corpus_type=product_evidence 时，非截图资料 allowed_usage 必须是 factual_evidence，"
                "截图资料 allowed_usage 必须是 display_material_only，"
                f"实际收到: {self.allowed_usage}"
            )
        if self.corpus_type == CorpusType.PRODUCT_EVIDENCE and not self.is_product_source:
            raise ValueError("corpus_type=product_evidence 时，is_product_source 必须为 True")
        if self.corpus_type == CorpusType.PRODUCT_EVIDENCE and self.is_reference_source:
            raise ValueError("corpus_type=product_evidence 时，is_reference_source 必须为 False")

        if self.source_type == SourceType.REFERENCE_SOFT_COPYRIGHT_DOC:
            if self.corpus_type != CorpusType.REFERENCE_STYLE:
                raise ValueError(
                    "source_type=reference_soft_copyright_doc 时，corpus_type 必须是 reference_style"
                )
            if self.allowed_usage != AllowedUsage.STYLE_ONLY:
                raise ValueError(
                    "source_type=reference_soft_copyright_doc 时，allowed_usage 必须是 style_only"
                )
            if not self.is_reference_source:
                raise ValueError(
                    "source_type=reference_soft_copyright_doc 时，is_reference_source 必须为 True"
                )
            if self.is_product_source:
                raise ValueError(
                    "source_type=reference_soft_copyright_doc 时，is_product_source 必须为 False"
                )

        if self.source_type == SourceType.SCREENSHOT:
            if self.corpus_type != CorpusType.PRODUCT_EVIDENCE:
                raise ValueError("source_type=screenshot 时，corpus_type 必须是 product_evidence")
            if self.allowed_usage != AllowedUsage.DISPLAY_MATERIAL_ONLY:
                raise ValueError("source_type=screenshot 时，allowed_usage 必须是 display_material_only")
            if not self.is_product_source:
                raise ValueError("source_type=screenshot 时，is_product_source 必须为 True")

        if self.source_type == SourceType.USER_NOTE:
            if self.corpus_type != CorpusType.PRODUCT_EVIDENCE:
                raise ValueError("source_type=user_note 时，corpus_type 必须是 product_evidence")
            if self.allowed_usage != AllowedUsage.FACTUAL_EVIDENCE:
                raise ValueError("source_type=user_note 时，allowed_usage 必须是 factual_evidence")
            if not self.is_product_source:
                raise ValueError("source_type=user_note 时，is_product_source 必须为 True")

        product_document_source_types = {
            SourceType.PRODUCT_INTRO_DOC,
            SourceType.PRD,
            SourceType.HLD,
            SourceType.DETAILED_DESIGN_DOC,
        }
        if self.source_type in product_document_source_types:
            if self.corpus_type != CorpusType.PRODUCT_EVIDENCE:
                raise ValueError(
                    f"source_type={self.source_type.value} 时，corpus_type 必须是 product_evidence"
                )
            if self.allowed_usage != AllowedUsage.FACTUAL_EVIDENCE:
                raise ValueError(
                    f"source_type={self.source_type.value} 时，allowed_usage 必须是 factual_evidence"
                )
            if not self.is_product_source:
                raise ValueError(
                    f"source_type={self.source_type.value} 时，is_product_source 必须为 True"
                )
            if self.is_reference_source:
                raise ValueError(
                    f"source_type={self.source_type.value} 时，is_reference_source 必须为 False"
                )

        return self


# ─────────────────────────────────────────────
# 2. ParsedAsset — 解析后的资产单元
# ─────────────────────────────────────────────


class ParsedAsset(BaseModel):
    """文件解析后的结果摘要，只保存引用路径，不保存全文内容。"""

    asset_id: str = Field(default_factory=_new_id)
    source_id: str
    asset_type: AssetType = AssetType.TEXT
    title: str | None = None
    summary: str | None = None
    # 指向 parsed/ 目录下的文本文件路径（相对路径字符串）
    extracted_text_ref: str | None = None
    # 指向图片文件路径
    image_ref: str | None = None
    page_number: int | None = None
    confidence: float = 1.0


# ─────────────────────────────────────────────
# 3. ProductSourceProfile — 产品资料读取结果
# ─────────────────────────────────────────────


class ProductSourceProfile(BaseModel):
    """ProductSourceAgent 的输出。Phase 2 的 URL 相关字段默认为空。"""

    uploaded_document_ids: list[str] = Field(default_factory=list)
    uploaded_screenshot_ids: list[str] = Field(default_factory=list)
    detected_navigation: list[str] = Field(default_factory=list)
    detected_page_titles: list[str] = Field(default_factory=list)
    detected_buttons: list[str] = Field(default_factory=list)
    detected_tables: list[dict[str, Any]] = Field(default_factory=list)
    detected_forms: list[dict[str, Any]] = Field(default_factory=list)
    detected_workflows: list[dict[str, Any]] = Field(default_factory=list)
    # ── Phase 2 预留字段，MVP 不使用 ──────────────────────────
    product_url_ids: list[str] = Field(default_factory=list)
    crawled_pages: list[dict[str, Any]] = Field(default_factory=list)
    captured_screenshot_ids: list[str] = Field(default_factory=list)
    failed_urls: list[str] = Field(default_factory=list)
    auth_required_pages: list[str] = Field(default_factory=list)
    crawl_risk_notes: list[str] = Field(default_factory=list)


# ─────────────────────────────────────────────
# 4. ReferenceStyleProfile — 参考软著风格分析结果
# ─────────────────────────────────────────────


class ReferenceStyleProfile(BaseModel):
    """
    ReferenceStyleAgent 的输出。

    只提炼写法特征，严禁提取对方产品名称、功能、业务描述。
    """

    common_chapter_structure: list[dict[str, Any]] = Field(default_factory=list)
    writing_style: str = ""
    screenshot_usage_pattern: str = ""
    operation_step_pattern: str = ""
    reusable_outline_pattern: list[dict[str, Any]] = Field(default_factory=list)
    prohibited_content_warning: list[str] = Field(default_factory=list)


# ─────────────────────────────────────────────
# 5. ProductProfile — 产品理解结果
# ─────────────────────────────────────────────


class ProductProfile(BaseModel):
    """ProductUnderstandingAgent 的输出，描述"产品是什么"，不决定目录。"""

    product_positioning: str = ""
    target_users: list[str] = Field(default_factory=list)
    core_modules: list[str] = Field(default_factory=list)
    core_workflows: list[dict[str, Any]] = Field(default_factory=list)
    business_objects: list[str] = Field(default_factory=list)
    page_list: list[str] = Field(default_factory=list)
    feature_list: list[str] = Field(default_factory=list)
    technical_keywords: list[str] = Field(default_factory=list)
    industry_keywords: list[str] = Field(default_factory=list)
    uncertain_features: list[str] = Field(default_factory=list)


# ─────────────────────────────────────────────
# 6. ProductFact — 产品事实点
# ─────────────────────────────────────────────


class ProductFact(BaseModel):
    """从自有产品资料中提取的单条产品事实。"""

    fact_id: str = Field(default_factory=_new_id)
    fact_type: ProductFactType = ProductFactType.FEATURE
    content: str
    source_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    is_confirmed: bool = False
    implementation_status: ImplementationStatus = ImplementationStatus.UNKNOWN
    capability_type: CapabilityType | None = None
    supporting_evidence_ids: list[str] = Field(default_factory=list)
    supporting_quotes: list[str] = Field(default_factory=list)
    reasoning: str | None = None
    validation_status: ValidationStatus = ValidationStatus.NEEDS_CONFIRMATION


class EvidenceSupport(BaseModel):
    """A verified quote from one product EvidenceItem."""

    evidence_id: str
    source_id: str
    quote: str = Field(min_length=1)
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)

    @field_validator("quote")
    @classmethod
    def _quote_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("EvidenceSupport.quote 不得为空")
        return value


class CapabilityValidationTrace(BaseModel):
    """Compact credential proving a capability passed grounding validation."""

    trace_id: str = Field(default_factory=_new_id)
    validator_name: str = "ProductCapabilityGroundingVerifier"
    source_grounded: bool
    semantic_grounded: bool
    verifier_supported: bool
    name_supported: bool
    capability_type_supported: bool
    implementation_status_supported: bool
    claim_hash: str = Field(min_length=1)
    evidence_supports_hash: str = Field(min_length=1)
    verified_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    reason: str | None = None


class ProductCapability(BaseModel):
    """Evidence-grounded semantic product capability."""

    capability_id: str
    name: str = Field(min_length=1)
    description: str = ""
    capability_type: CapabilityType = CapabilityType.OTHER
    implementation_status: ImplementationStatus = ImplementationStatus.UNKNOWN
    evidence_supports: list[EvidenceSupport] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    validation_status: ValidationStatus = ValidationStatus.NEEDS_CONFIRMATION
    reasoning: str | None = None
    validation_trace: CapabilityValidationTrace | None = None

    @field_validator("name")
    @classmethod
    def _name_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("ProductCapability.name 不得为空")
        return value

    @model_validator(mode="after")
    def _validated_current_requires_evidence(self) -> ProductCapability:
        if (
            self.implementation_status == ImplementationStatus.CURRENT
            and self.validation_status == ValidationStatus.VALIDATED
            and not self.evidence_supports
        ):
            raise ValueError("validated current ProductCapability 必须包含 evidence_supports")
        return self


# ─────────────────────────────────────────────
# 7. EvidenceItem — 证据单元（核心隔离对象）
# ─────────────────────────────────────────────


class EvidenceItem(BaseModel):
    """
    证据单元，写入 Qdrant 时以此为准。

    corpus_type / allowed_usage 必须与来源 SourceItem 保持一致，
    是 WriterAgent / AuditAgent 过滤检索的关键字段。
    """

    evidence_id: str = Field(default_factory=_new_id)
    source_id: str
    source_type: SourceType
    file_type: FileType
    evidence_type: EvidenceType
    corpus_type: CorpusType
    allowed_usage: AllowedUsage
    evidence_strength: EvidenceStrength = EvidenceStrength.MEDIUM

    function_name: str | None = None
    related_module: str | None = None
    related_chapter: str | None = None
    # 指向 evidence/ 目录下的内容文件（相对路径）
    content_ref: str | None = None
    summary: str | None = None
    extracted_facts: list[dict[str, Any]] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    source_location: str | None = None
    location: str | None = None
    screenshot_id: str | None = None
    confidence: float = 1.0
    is_confirmed: bool = False
    needs_human_confirmation: bool = False
    notes: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_evidence_isolation(self) -> EvidenceItem:
        if (
            self.corpus_type == CorpusType.REFERENCE_STYLE
            and self.allowed_usage != AllowedUsage.STYLE_ONLY
        ):
            raise ValueError(
                "corpus_type=reference_style 时，EvidenceItem.allowed_usage 必须是 style_only"
            )
        if (
            self.corpus_type == CorpusType.REFERENCE_STYLE
            and self.evidence_type != EvidenceType.REFERENCE_STYLE_ONLY
        ):
            raise ValueError(
                "corpus_type=reference_style 时，evidence_type 必须是 reference_style_only"
            )
        if (
            self.corpus_type == CorpusType.REFERENCE_STYLE
            and self.evidence_strength != EvidenceStrength.NOT_ALLOWED_AS_FACT
        ):
            raise ValueError(
                "corpus_type=reference_style 时，evidence_strength 必须是 not_allowed_as_fact"
            )

        if (
            self.corpus_type == CorpusType.PRODUCT_EVIDENCE
            and self.evidence_type != EvidenceType.PRODUCT_SCREENSHOT
            and self.allowed_usage != AllowedUsage.FACTUAL_EVIDENCE
        ):
            raise ValueError(
                "corpus_type=product_evidence 时，非截图 EvidenceItem.allowed_usage 必须是 factual_evidence"
            )
        if (
            self.corpus_type == CorpusType.PRODUCT_EVIDENCE
            and self.evidence_type == EvidenceType.REFERENCE_STYLE_ONLY
        ):
            raise ValueError(
                "corpus_type=product_evidence 时，evidence_type 不得是 reference_style_only"
            )
        if (
            self.corpus_type == CorpusType.PRODUCT_EVIDENCE
            and self.evidence_type != EvidenceType.PRODUCT_SCREENSHOT
            and self.evidence_strength == EvidenceStrength.NOT_ALLOWED_AS_FACT
        ):
            raise ValueError(
                "corpus_type=product_evidence 时，非截图 evidence_strength 不得是 not_allowed_as_fact"
            )

        if self.evidence_type == EvidenceType.REFERENCE_STYLE_ONLY:
            if self.corpus_type != CorpusType.REFERENCE_STYLE:
                raise ValueError(
                    "evidence_type=reference_style_only 时，corpus_type 必须是 reference_style"
                )
            if self.allowed_usage != AllowedUsage.STYLE_ONLY:
                raise ValueError(
                    "evidence_type=reference_style_only 时，allowed_usage 必须是 style_only"
                )
            if self.evidence_strength != EvidenceStrength.NOT_ALLOWED_AS_FACT:
                raise ValueError(
                    "evidence_type=reference_style_only 时，evidence_strength 必须是 not_allowed_as_fact"
                )

        if self.evidence_type == EvidenceType.PRODUCT_DOCUMENT:
            if self.corpus_type != CorpusType.PRODUCT_EVIDENCE:
                raise ValueError(
                    "evidence_type=product_document 时，corpus_type 必须是 product_evidence"
                )
            if self.allowed_usage != AllowedUsage.FACTUAL_EVIDENCE:
                raise ValueError(
                    "evidence_type=product_document 时，allowed_usage 必须是 factual_evidence"
                )

        if self.evidence_type == EvidenceType.PRODUCT_SCREENSHOT:
            if self.source_type != SourceType.SCREENSHOT:
                raise ValueError(
                    "evidence_type=product_screenshot 时，source_type 必须是 screenshot"
                )
            if self.corpus_type != CorpusType.PRODUCT_EVIDENCE:
                raise ValueError(
                    "evidence_type=product_screenshot 时，corpus_type 必须是 product_evidence"
                )
            if self.allowed_usage != AllowedUsage.DISPLAY_MATERIAL_ONLY:
                raise ValueError(
                    "evidence_type=product_screenshot 时，allowed_usage 必须是 display_material_only"
                )
            if self.evidence_strength != EvidenceStrength.NOT_ALLOWED_AS_FACT:
                raise ValueError(
                    "evidence_type=product_screenshot 时，evidence_strength 必须是 not_allowed_as_fact"
                )

        if self.evidence_type == EvidenceType.USER_CONFIRMATION:
            if self.source_type != SourceType.USER_NOTE:
                raise ValueError("evidence_type=user_confirmation 时，source_type 必须是 user_note")
            if self.corpus_type != CorpusType.PRODUCT_EVIDENCE:
                raise ValueError(
                    "evidence_type=user_confirmation 时，corpus_type 必须是 product_evidence"
                )
            if self.allowed_usage != AllowedUsage.FACTUAL_EVIDENCE:
                raise ValueError(
                    "evidence_type=user_confirmation 时，allowed_usage 必须是 factual_evidence"
                )
        # product_url_page / product_url 是 Phase 2 预留；MVP 默认 State 和默认流程不生成。
        return self


# ─────────────────────────────────────────────
# 8. DiagnosisResult — 软件类型诊断结果
# ─────────────────────────────────────────────


class DiagnosisResult(BaseModel):
    """SoftwareDiagnosisAgent 的输出，判断主类型、增强标签、推荐文档写法。"""

    primary_type: str = ""
    primary_type_confidence: float = 0.0
    business_objects: list[str] = Field(default_factory=list)
    enhancement_tags: list[str] = Field(default_factory=list)
    recommended_doc_style: str = ""
    alternative_doc_styles: list[str] = Field(default_factory=list)
    diagnosis_reasons: list[str] = Field(default_factory=list)
    risk_notes: list[str] = Field(default_factory=list)


# ─────────────────────────────────────────────
# 9. TemplateStrategy — 模板策略
# ─────────────────────────────────────────────


class TemplateStrategy(BaseModel):
    """TemplateStrategyAgent 的输出，推荐软著文档模板和章节策略。"""

    base_template_id: str = ""
    base_template_name: str = ""
    enhancement_pack_ids: list[str] = Field(default_factory=list)
    excluded_template_ids: list[str] = Field(default_factory=list)
    recommended_chapters: list[str] = Field(default_factory=list)
    optional_chapters: list[str] = Field(default_factory=list)
    risk_chapters: list[str] = Field(default_factory=list)
    recommendation_reason: list[str] = Field(default_factory=list)


# ─────────────────────────────────────────────
# 10. HumanConfirmation — 用户确认记录
# ─────────────────────────────────────────────


class HumanConfirmation(BaseModel):
    """一次用户确认交互的完整记录。"""

    confirmation_id: str = Field(default_factory=_new_id)
    confirmation_type: ConfirmationType
    prompt: str
    options: list[str] = Field(default_factory=list)
    user_choice: str | None = None
    user_notes: str | None = None
    confirmed_at: str | None = None
    status: ConfirmationStatus = ConfirmationStatus.PENDING
    metadata: dict[str, Any] = Field(default_factory=dict)


class TemplateConfirmationDecision(BaseModel):
    """Human-confirmed template and top-level chapter decision."""

    decision_id: str = Field(default_factory=_new_id)
    accepted_recommendation: bool = True
    selected_base_template_id: str = Field(min_length=1)
    selected_base_template_name: str = Field(min_length=1)
    selected_enhancement_pack_ids: list[str] = Field(default_factory=list)
    selected_top_level_chapters: list[str] = Field(min_length=1)
    selected_optional_chapters: list[str] = Field(default_factory=list)
    acknowledged_risk_chapters: list[str] = Field(default_factory=list)
    excluded_chapters: list[str] = Field(default_factory=list)
    manual_overrides: dict[str, list[str]] = Field(default_factory=dict)
    user_notes: str | None = None
    risk_acknowledged: bool = False
    confirmed_at: str | None = None

    @field_validator(
        "selected_top_level_chapters",
        "selected_enhancement_pack_ids",
        "selected_optional_chapters",
        "acknowledged_risk_chapters",
        "excluded_chapters",
    )
    @classmethod
    def _lists_must_not_contain_blank_values(cls, values: list[str]) -> list[str]:
        if any(not value.strip() for value in values):
            raise ValueError("确认决策列表不得包含空字符串")
        return values


# ─────────────────────────────────────────────
# 11. FrozenDocPlan — 冻结文档计划（生成合同）
# ─────────────────────────────────────────────


class FrozenDocPlan(BaseModel):
    """
    用户确认后由 OrchestratorAgent 生成并锁定的文档生成合同。

    OutlineAgent / WriterAgent / AuditAgent 都必须以此为准，不得擅自修改一级目录。
    """

    plan_id: str = Field(default_factory=_new_id)
    project_id: str = ""
    plan_version: str = "v1"
    locked_status: LockedStatus = LockedStatus.DRAFT
    locked_at: str | None = None
    locked_by: LockedBy = LockedBy.ORCHESTRATOR

    software_identity: dict[str, Any] = Field(default_factory=dict)
    diagnosis_snapshot: dict[str, Any] = Field(default_factory=dict)
    template_decision: dict[str, Any] = Field(default_factory=dict)
    chapter_policy: dict[str, Any] = Field(default_factory=dict)
    feature_policy: dict[str, Any] = Field(default_factory=dict)
    evidence_policy: dict[str, Any] = Field(default_factory=dict)
    screenshot_policy: dict[str, Any] = Field(default_factory=dict)
    writing_policy: dict[str, Any] = Field(default_factory=dict)
    quality_gate_policy: dict[str, Any] = Field(default_factory=dict)
    downstream_permissions: dict[str, Any] = Field(default_factory=dict)
    missing_information: list[dict[str, Any]] = Field(default_factory=list)
    risk_notes: list[str] = Field(default_factory=list)


# ─────────────────────────────────────────────
# 12. DocumentOutline — 文档大纲
# ─────────────────────────────────────────────


class DocumentOutline(BaseModel):
    """OutlineAgent 基于 FrozenDocPlan 生成的详细目录，不允许自由修改一级目录。"""

    outline_id: str = Field(default_factory=_new_id)
    based_on_plan_id: str = ""
    chapters: list[dict[str, Any]] = Field(default_factory=list)
    required_evidence: list[dict[str, Any]] = Field(default_factory=list)
    required_screenshots: list[str] = Field(default_factory=list)
    estimated_pages: int | None = None


# ─────────────────────────────────────────────
# 13. SectionPlan — 章节写作计划
# ─────────────────────────────────────────────


class SectionPlan(BaseModel):
    """单个章节的写作规划，供 WriterAgent 逐章执行。"""

    section_id: str = Field(default_factory=_new_id)
    chapter_title: str = ""
    section_title: str = ""
    section_level: int = 2
    parent_section_title: str | None = None
    section_path: list[str] = Field(default_factory=list)
    writing_goal: str = ""
    required_evidence_ids: list[str] = Field(default_factory=list)
    required_capability_ids: list[str] = Field(default_factory=list)
    required_fact_ids: list[str] = Field(default_factory=list)
    needs_human_confirmation: bool = False
    required_screenshot_ids: list[str] = Field(default_factory=list)
    writing_constraints: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_section_plan_contract(self) -> SectionPlan:
        if not self.section_id.strip():
            raise ValueError("SectionPlan.section_id 不得为空")
        if not self.chapter_title.strip():
            raise ValueError("SectionPlan.chapter_title 不得为空")
        if not self.section_title.strip():
            raise ValueError("SectionPlan.section_title 不得为空")
        if not self.writing_goal.strip():
            raise ValueError("SectionPlan.writing_goal 不得为空")
        if self.section_level not in {2, 3}:
            raise ValueError("SectionPlan.section_level 必须为 2 或 3")
        if not self.section_path and self.section_level == 2:
            self.section_path = [self.chapter_title, self.section_title]
        if len(self.section_path) < 2:
            raise ValueError("SectionPlan.section_path 必须包含一级章节和当前 section")
        return self


# ─────────────────────────────────────────────
# 14. ScreenshotBinding — 截图绑定关系
# ─────────────────────────────────────────────


class ScreenshotBinding(BaseModel):
    """ScreenshotBindingAgent 输出的截图与章节绑定关系。"""

    screenshot_id: str = Field(default_factory=_new_id)
    source_id: str = ""
    suggested_chapter: str = ""
    suggested_section: str = ""
    screenshot_description: str = ""
    confidence: float = 1.0
    status: ScreenshotBindingStatus = ScreenshotBindingStatus.CANDIDATE


# ─────────────────────────────────────────────
# 15. MissingInformationItem — 缺失信息条目
# ─────────────────────────────────────────────


class MissingInformationItem(BaseModel):
    """PlanQualityGate 需要向用户反问的缺失信息。每次最多生成 5~8 条。"""

    item_id: str = Field(default_factory=_new_id)
    question: str
    reason: str = ""
    severity: AuditSeverity = AuditSeverity.MAJOR
    related_chapter: str | None = None
    related_feature: str | None = None
    status: MissingInformationStatus = MissingInformationStatus.PENDING


# ─────────────────────────────────────────────
# 16. DraftVersion — 草稿版本记录
# ─────────────────────────────────────────────


class DraftVersion(BaseModel):
    """一次草稿版本的元信息，content_ref 指向 drafts/ 目录下的文件路径。"""

    draft_id: str = Field(default_factory=_new_id)
    version_label: DraftVersionLabel = DraftVersionLabel.V1
    based_on_plan_id: str = ""
    based_on_outline_id: str = ""
    # 指向 drafts/ 目录下的结构化 JSON 文件（相对路径）
    content_ref: str = ""
    created_at: str = Field(default_factory=_utcnow_iso)
    revision_notes: str | None = None
    source_audit_report_id: str | None = None


# ─────────────────────────────────────────────
# 17. FigureSlotResult — v1 草稿后的配图补图规划
# ─────────────────────────────────────────────


class FigureSlotItem(BaseModel):
    """一个建议补图图位，不绑定、不读取、不证明真实截图。"""

    model_config = ConfigDict(extra="forbid")

    slot_id: str
    section_id: str
    section_path: list[str]
    section_title: str
    recommended_caption: str
    recommended_screenshot: str
    reason: str
    required: bool
    status: Literal["missing"] = "missing"
    user_action: str
    warnings: list[str] = Field(default_factory=list)


class FigureSlotSummary(BaseModel):
    """配图补图清单统计。"""

    model_config = ConfigDict(extra="forbid")

    total_slots: int = 0
    required_slots: int = 0
    optional_slots: int = 0
    missing_slots: int = 0


class FigureSlotSafetyReport(BaseModel):
    """Sprint 10 输出边界证明。"""

    model_config = ConfigDict(extra="forbid")

    body_unchanged: bool = True
    does_not_claim_existing_images: bool = True
    does_not_modify_citations: bool = True
    does_not_modify_evidence_ids_used: bool = True
    does_not_modify_draft_content: bool = True
    does_not_bind_real_screenshots: bool = True
    does_not_use_ocr: bool = True
    does_not_use_vision_model: bool = True
    warnings: list[str] = Field(default_factory=list)


class FigureSlotResult(BaseModel):
    """FigureSlotPlanner 的独立输出，不属于 DraftVersion。"""

    model_config = ConfigDict(extra="forbid")

    result_id: str
    draft_version: Literal["v1"] = "v1"
    source_draft_ref: str = "drafts/draft_v1.json"
    created_at: str = Field(default_factory=_utcnow_iso)
    figure_slots: list[FigureSlotItem] = Field(default_factory=list)
    summary: FigureSlotSummary = Field(default_factory=FigureSlotSummary)
    safety_report: FigureSlotSafetyReport = Field(default_factory=FigureSlotSafetyReport)


# ─────────────────────────────────────────────
# 18. DraftAuditReport — v1 草稿审计结果
# ─────────────────────────────────────────────


class AuditFinding(BaseModel):
    """Sprint 11 结构化审计 finding。"""

    model_config = ConfigDict(extra="forbid")

    finding_id: str
    severity: AuditSeverity
    category: AuditCategory
    section_id: str | None = None
    section_path: list[str] = Field(default_factory=list)
    message: str
    claim_text: str | None = None
    evidence_id: str | None = None
    quote: str | None = None
    recommendation: str
    detector: Literal["deterministic", "semantic_llm", "validator"]
    metadata: dict[str, Any] = Field(default_factory=dict)


class AuditSectionSummary(BaseModel):
    """单节审计统计。"""

    model_config = ConfigDict(extra="forbid")

    section_id: str
    section_title: str
    blocker_count: int = 0
    major_count: int = 0
    minor_count: int = 0
    suggestion_count: int = 0


class AuditReportSummary(BaseModel):
    """审计报告总体统计。"""

    model_config = ConfigDict(extra="forbid")

    total_findings: int = 0
    blocker_count: int = 0
    major_count: int = 0
    minor_count: int = 0
    suggestion_count: int = 0
    audited_section_count: int = 0
    figure_slot_count: int = 0


class AuditSafetyReport(BaseModel):
    """AuditAgent 输出边界证明。"""

    model_config = ConfigDict(extra="forbid")

    draft_unchanged: bool = True
    figure_slots_unchanged: bool = True
    does_not_modify_citations: bool = True
    does_not_modify_evidence_ids_used: bool = True
    does_not_use_reference_style_as_fact: bool = True
    warnings: list[str] = Field(default_factory=list)


class DraftAuditReport(BaseModel):
    """Sprint 11/12 草稿审计报告，不属于 DraftVersion。"""

    model_config = ConfigDict(extra="forbid")

    report_id: str
    draft_version: Literal["v1", "v2", "v3"] = "v1"
    source_draft_ref: str = "drafts/draft_v1.json"
    source_draft_hash: str
    source_figure_slots_ref: str = "drafts/figure_slots_v1.json"
    source_figure_slots_hash: str
    created_at: str = Field(default_factory=_utcnow_iso)
    overall_passed: bool = False
    findings: list[AuditFinding] = Field(default_factory=list)
    section_summaries: list[AuditSectionSummary] = Field(default_factory=list)
    summary: AuditReportSummary = Field(default_factory=AuditReportSummary)
    safety_report: AuditSafetyReport = Field(default_factory=AuditSafetyReport)


# ─────────────────────────────────────────────
# 19. AuditIssue — 审计问题条目
# ─────────────────────────────────────────────


class AuditIssue(BaseModel):
    """单条审计问题，包含级别、类型、位置和修复建议。"""

    issue_id: str = Field(default_factory=_new_id)
    issue_type: AuditIssueType = AuditIssueType.OTHER
    severity: AuditSeverity
    location: str | None = None
    description: str
    suggested_fix: str = ""


# ─────────────────────────────────────────────
# 20. AuditReport — 审计报告
# ─────────────────────────────────────────────


class AuditReport(BaseModel):
    """
    AuditAgent 对一版草稿的完整审计报告。

    score = 100 - blocker_count*30 - major_count*8 - minor_count*3
    Blocker 具有一票否决权（即使分数 ≥ 85 也不得通过）。
    """

    audit_report_id: str = Field(default_factory=_new_id)
    draft_id: str = ""
    audit_round: int = 1
    issues: list[AuditIssue] = Field(default_factory=list)
    score: int = 100
    blocker_count: int = 0
    major_count: int = 0
    minor_count: int = 0
    passed: bool = False
    recommended_next_action: NextAction = NextAction.REVISE_DRAFT


# ─────────────────────────────────────────────
# 21. QualityGateReport — 质量门禁报告
# ─────────────────────────────────────────────


class QualityGateReport(BaseModel):
    """PlanQualityGate 或 DraftQualityGate 的检查结果。"""

    gate_id: str = Field(default_factory=_new_id)
    gate_type: GateType
    target_id: str = ""
    passed: bool = False
    checklist_results: list[dict[str, Any]] = Field(default_factory=list)
    blocker_issues: list[str] = Field(default_factory=list)
    major_issues: list[str] = Field(default_factory=list)
    minor_issues: list[str] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    required_user_questions: list[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=_utcnow_iso)
    summary: str = ""
    next_action: NextAction = NextAction.STOP


class DraftQualityGateFindingSummary(BaseModel):
    """Finding counts copied from one validated audit report."""

    model_config = ConfigDict(extra="forbid")

    blocker: int = 0
    major: int = 0
    minor: int = 0
    suggestion: int = 0


class DraftQualityGateReport(BaseModel):
    """Sprint 12 decision derived only from a validated DraftAuditReport."""

    model_config = ConfigDict(extra="forbid")

    report_version: Literal["v1"] = "v1"
    draft_version: Literal["v1", "v2", "v3"]
    source_audit_report_path: str
    source_audit_report_hash: str
    source_draft_ref: str
    source_draft_hash: str
    source_figure_slots_ref: str
    source_figure_slots_hash: str
    audit_overall_passed: bool
    passed: bool
    decision: DraftQualityGateDecision
    severity_counts: DraftQualityGateFindingSummary
    blocking_finding_ids: list[str] = Field(default_factory=list)
    major_finding_ids: list[str] = Field(default_factory=list)
    minor_finding_ids: list[str] = Field(default_factory=list)
    suggestion_finding_ids: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    fail_closed_reason: str | None = None
    created_at: str = Field(default_factory=_utcnow_iso)
    next_workflow_status: WorkflowStatus
    next_action: NextAction


# ─────────────────────────────────────────────
# 22. ExportResult — 导出结果
# ─────────────────────────────────────────────


class ExportResult(BaseModel):
    """ExportAgent 的输出，记录最终 DOCX 的路径和类型。"""

    export_id: str = Field(default_factory=_new_id)
    export_type: ExportType = ExportType.FINAL
    docx_path: str | None = None
    pdf_path: str | None = None          # MVP 不导出 PDF，预留字段
    risk_report_path: str | None = None  # MVP 不单独导出审计报告
    exported_at: str | None = None
    export_notes: list[str] = Field(default_factory=list)


class ExportManifest(BaseModel):
    """Internal Sprint 13 DOCX export lineage manifest."""

    model_config = ConfigDict(extra="forbid")

    export_id: str = Field(default_factory=_new_id)
    export_type: Literal["normal", "risk"]
    draft_version: Literal["v1", "v2", "v3"]
    output_docx_path: str
    output_docx_hash: str
    source_draft_ref: str
    source_draft_hash: str
    source_figure_slots_ref: str
    source_figure_slots_hash: str
    source_audit_report_ref: str
    source_audit_report_hash: str
    source_quality_gate_report_ref: str
    source_quality_gate_report_hash: str
    source_revision_trace_refs: list[str] = Field(default_factory=list)
    source_revision_trace_hashes: list[str] = Field(default_factory=list)
    quality_gate_passed: bool
    audit_overall_passed: bool
    unresolved_blocker_count: int = 0
    unresolved_major_count: int = 0
    risk_notice: str | None = None
    created_at: str = Field(default_factory=_utcnow_iso)


# ─────────────────────────────────────────────
# 23. StateTransitionLog — 状态流转日志
# ─────────────────────────────────────────────


class StateTransitionLog(BaseModel):
    """记录每次工作流状态流转，用于调试和任务恢复。"""

    from_status: WorkflowStatus
    to_status: WorkflowStatus
    node_name: str = ""
    reason: str = ""
    created_at: str = Field(default_factory=_utcnow_iso)


# ─────────────────────────────────────────────
# 24. DocForgeState — 全局任务状态（核心对象）
# ─────────────────────────────────────────────


def _generate_run_id() -> str:
    """在 schemas 内部使用的 run_id 生成器，避免循环引用。"""
    import secrets
    from datetime import datetime

    ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    suffix = secrets.token_hex(2)
    return f"{ts}_{suffix}"


class DocForgeState(BaseModel):
    """
    WF-02 工作流的全局业务状态。

    持久化边界：
    - 本对象保存至 data/runs/{run_id}/state.json
    - 不保存完整原始文档、完整截图、完整 DOCX、大段原文
    - 只保存路径、ID、结构化摘要和状态指针
    - Qdrant 负责证据语义检索，本对象不重复存储证据全文
    """

    # ── 基础任务信息 ───────────────────────────────────────
    run_id: str = Field(default_factory=_generate_run_id)
    project_id: str = ""
    project_name: str = ""
    target_doc_type: str = "software_copyright_doc"
    target_product_name: str = ""
    user_goal: str = "生成软件著作权文档"
    output_requirements: dict[str, Any] = Field(
        default_factory=lambda: {
            "output_format": "docx",
            "export_pdf": False,
            "export_markdown": False,
        }
    )

    # ── WF-02 状态机控制 ──────────────────────────────────
    workflow_status: WorkflowStatus = WorkflowStatus.CREATED
    next_action: NextAction = NextAction.INGEST_MATERIALS
    status_history: list[StateTransitionLog] = Field(default_factory=list)

    # ── 资料登记表（不直接存全文） ─────────────────────────
    source_registry: list[SourceItem] = Field(default_factory=list)
    reference_source_ids: list[str] = Field(default_factory=list)
    product_source_ids: list[str] = Field(default_factory=list)
    screenshot_source_ids: list[str] = Field(default_factory=list)
    # Phase 2 预留，MVP 默认为空，不进入工作流
    product_url_source_ids: list[str] = Field(default_factory=list)

    # ── 解析结果 ──────────────────────────────────────────
    parsed_assets: list[ParsedAsset] = Field(default_factory=list)
    # collection 名自动派生为 docforge_{run_id}，见 model_validator
    qdrant_collection: str = ""

    # ── 产品资料读取结果 ──────────────────────────────────
    product_source_profile: ProductSourceProfile = Field(
        default_factory=ProductSourceProfile
    )

    # ── 参考软著风格画像 ──────────────────────────────────
    style_profile: ReferenceStyleProfile = Field(
        default_factory=ReferenceStyleProfile
    )

    # ── 产品理解结果 ──────────────────────────────────────
    product_profile: ProductProfile = Field(default_factory=ProductProfile)
    product_capabilities: list[ProductCapability] = Field(default_factory=list)
    product_facts: list[ProductFact] = Field(default_factory=list)
    evidence_map: list[EvidenceItem] = Field(default_factory=list)

    # ── 软件类型诊断与模板策略 ────────────────────────────
    diagnosis_result: DiagnosisResult | None = None
    template_strategy: TemplateStrategy | None = None

    # ── 用户确认 ──────────────────────────────────────────
    human_confirmations: list[HumanConfirmation] = Field(default_factory=list)
    pending_human_questions: list[str] = Field(default_factory=list)
    missing_information: list[MissingInformationItem] = Field(default_factory=list)

    # ── 冻结计划（WF-02 核心控制对象） ───────────────────
    frozen_doc_plan: FrozenDocPlan | None = None

    # ── 大纲和写作计划 ────────────────────────────────────
    outline: DocumentOutline | None = None
    section_plan: list[SectionPlan] = Field(default_factory=list)

    # ── 截图绑定 ──────────────────────────────────────────
    screenshot_map: list[ScreenshotBinding] = Field(default_factory=list)

    # ── Plan Quality Gate ─────────────────────────────────
    plan_quality_gate_report: QualityGateReport | None = None
    plan_quality_gate_passed: bool = False

    # ── 草稿版本 ──────────────────────────────────────────
    draft_versions: list[DraftVersion] = Field(default_factory=list)
    current_draft_id: str | None = None
    current_draft_version: str | None = None
    figure_slots_ref: str | None = None
    figure_slots_result_id: str | None = None
    audit_report_ref: str | None = None
    audit_report_result_id: str | None = None
    draft_quality_gate_report_ref: str | None = None

    # ── Draft Audit / Draft Quality Gate ─────────────────
    audit_reports: list[AuditReport] = Field(default_factory=list)
    draft_quality_gate_reports: list[QualityGateReport] = Field(default_factory=list)
    current_score: int | None = None
    blocker_issues: list[str] = Field(default_factory=list)
    major_issues: list[str] = Field(default_factory=list)
    minor_issues: list[str] = Field(default_factory=list)

    # ── 循环控制 ──────────────────────────────────────────
    revision_round: int = 0
    max_revision_round: int = 3

    # ── 导出结果 ──────────────────────────────────────────
    export_result: ExportResult | None = None
    final_doc_path: str | None = None
    final_pdf_path: str | None = None      # MVP 不导出 PDF
    risk_report_path: str | None = None

    # ── 异常与调试 ────────────────────────────────────────
    errors: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _init_derived_ids(self) -> DocForgeState:
        """project_id / qdrant_collection 自动派生，保证 MVP 状态契约。"""
        if not self.project_id:
            self.project_id = f"proj_{self.run_id}"

        expected = f"docforge_{self.run_id}"
        if not self.qdrant_collection:
            self.qdrant_collection = expected
        elif self.qdrant_collection != expected:
            raise ValueError(
                f"qdrant_collection 必须是 {expected}，实际收到: {self.qdrant_collection}"
            )
        return self
