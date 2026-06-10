export type SourceType =
  | "reference_soft_copyright_doc"
  | "product_intro_doc"
  | "prd"
  | "hld"
  | "detailed_design_doc"
  | "screenshot"
  | "user_note"
  | "other";

export type FileType =
  | "docx"
  | "pdf"
  | "md"
  | "txt"
  | "html"
  | "png"
  | "jpg"
  | "jpeg"
  | "webp"
  | "none"
  | "other";

export type CorpusType = "reference_style" | "product_evidence";

export type AllowedUsage = "style_only" | "factual_evidence" | "display_material_only";

export type ParseStatus = "pending" | "parsed" | "failed" | "skipped" | "saved";

export interface SourceUsagePolicy {
  label: string;
  allowedUse: string;
  riskBoundary: string;
  badgeType: "info" | "success" | "warning";
}

export interface SourceItem {
  sourceId: string;
  runId: string;
  sourceType: SourceType;
  fileType: FileType;
  corpusType: CorpusType;
  allowedUsage: AllowedUsage;
  fileName: string;
  filePath?: string;
  fileSize?: number;
  uploadedAt: string;
  parseStatus: ParseStatus;
  parseError?: string | null;
  statusLabel: string;
  usagePolicy: SourceUsagePolicy;
  notes?: string;
  metadata?: Record<string, unknown>;
}

export interface ExportArtifact {
  artifactId: string;
  name: string;
  type: "normal_docx" | "risk_docx";
  statusLabel: string;
  downloadable: boolean;
}

export interface RunSummary {
  runId: string;
  projectName: string;
  taskName: string;
  stageLabel: string;
  healthLabel: string;
  healthTone: "success" | "warning" | "danger" | "info";
}

export interface RunListItem {
  runId: string;
  projectName: string;
  taskName: string;
  stageLabel: string;
  createdAt: string;
  updatedAt: string;
}

export type AgentActionType =
  | "open_upload"
  | "parse_sources"
  | "analyze_reference_style"
  | "understand_product"
  | "extract_evidence"
  | "diagnose_software_type"
  | "recommend_template"
  | "ask_human_confirmation"
  | "freeze_doc_plan"
  | "create_outline"
  | "run_plan_quality_gate"
  | "ask_missing_information"
  | "write_draft"
  | "plan_figure_slots"
  | "audit_draft"
  | "run_draft_quality_gate"
  | "revise_draft"
  | "audit_revised_draft"
  | "export_docx"
  | "export_final_doc"
  | "export_risk_doc"
  | "confirm-product-type"
  | "confirm-doc-plan"
  | "export-final-docx"
  | "export-risk-docx"
  | "refresh_diagnostics"
  | "start_parse_sources"
  | "use_agent_recommendation"
  | "use_user_selection"
  | "view_difference_reason"
  | "confirm_doc_plan"
  | "adjust_doc_plan"
  | "regenerate_doc_plan"
  | "view_risk_detail"
  | "export_risk_docx"
  | "return_to_revision"
  | "download_risk_docx"
  | "view_generation_record"
  | "open_upload_mock"
  | "export_entry_mock"
  | "update_setting_mock";

export interface AgentCardAction {
  actionId: string;
  actionType: AgentActionType;
  label: string;
  variant: "primary" | "secondary" | "danger";
  disabled?: boolean;
  requiresConfirmation?: boolean;
  description?: string;
}

export interface WorkspaceAction {
  actionId: string;
  actionType: AgentActionType;
  label: string;
  primary: boolean;
  disabled: boolean;
  description?: string;
}

export type AgentCardType =
  | "source_received"
  | "product_type_decision"
  | "doc_plan_confirm"
  | "risk_check"
  | "export_result"
  | "error_recovery";

export interface BaseAgentCard {
  cardId: string;
  cardType: AgentCardType;
  title: string;
  summary?: string;
  payload?: Record<string, unknown>;
  actions: AgentCardAction[];
}

export interface SourceReceivedCard extends BaseAgentCard {
  cardType: "source_received";
  counts: {
    externalReferences: number;
    productMaterials: number;
    screenshots: number;
  };
  nextStepLabel: string;
}

export interface ProductTypeDecisionCard extends BaseAgentCard {
  cardType: "product_type_decision";
  userChoice: string;
  agentJudgement: string;
  recommendedType: string;
  differenceReasons: string[];
}

export interface DocPlanConfirmCard extends BaseAgentCard {
  cardType: "doc_plan_confirm";
  sections: string[];
}

export interface RiskSummary {
  blocker: number;
  major: number;
  minor: number;
  suggestion: number;
  conclusion: string;
}

export interface RiskCheckCard extends BaseAgentCard {
  cardType: "risk_check";
  riskSummary: RiskSummary;
}

export interface ExportResultCard extends BaseAgentCard {
  cardType: "export_result";
  artifactName: string;
  description: string;
}

export interface ErrorRecoveryCard extends BaseAgentCard {
  cardType: "error_recovery";
  errorMessage: string;
  recoverable: boolean;
}

export type AgentCard =
  | SourceReceivedCard
  | ProductTypeDecisionCard
  | DocPlanConfirmCard
  | RiskCheckCard
  | ExportResultCard
  | ErrorRecoveryCard;

export type RunEventType =
  | "user_message"
  | "agent_message"
  | "source_received"
  | "product_type_decision"
  | "doc_plan_confirm"
  | "risk_check_result"
  | "export_ready"
  | "setting_updated"
  | "action_triggered"
  | "error"
  | "system_notice";

export interface AgentMessage {
  messageId: string;
  runId: string;
  role: "user" | "agent" | "system";
  content: string;
  createdAt: string;
  createdAtLabel: string;
  eventId?: string;
  eventType?: RunEventType;
  isUserVisible?: boolean;
  card?: AgentCard;
}

export type ProductTypeOption =
  | "saas_web_platform"
  | "ai_platform"
  | "data_platform"
  | "industrial_software"
  | "tool_software"
  | "agent_decide";

export type DocOutputType =
  | "user_manual"
  | "product_feature_description"
  | "technical_design";

export type ReferenceStyleStrength = "weak" | "medium" | "strong";

export type LlmModelOption = "qwen" | "deepseek";

export type EmbeddingModelOption = "jina";

export interface ApiKeyConfigState {
  llmModel: LlmModelOption;
  llmApiKey: string;
  embeddingModel: EmbeddingModelOption;
  embeddingApiKey: string;
}

export interface WorkspaceSettings {
  productTypeHint: ProductTypeOption;
  docOutputType: DocOutputType;
  referenceStyleStrength: ReferenceStyleStrength;
}

export interface DiagnosticSummary {
  healthLabel: string;
  stageLabel: string;
  nextSuggestion: string;
}

export interface WorkspaceLastError {
  message: string;
  occurredAt: string;
  recoverable: boolean;
}

export interface WorkspaceState {
  runSummary: RunSummary;
  sources: SourceItem[];
  exportArtifacts: ExportArtifact[];
  messages: AgentMessage[];
  settings: WorkspaceSettings;
  diagnostics: DiagnosticSummary;
  availableActions: WorkspaceAction[];
  primaryAction?: WorkspaceAction;
  error: string | null;
  lastError?: WorkspaceLastError | null;
}
