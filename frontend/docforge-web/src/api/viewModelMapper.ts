import type {
  AgentActionApi,
  AgentMessageApi,
  DiagnosticSummaryApi,
  ExportArtifactApi,
  LastErrorApi,
  RunListItemApi,
  RunSummaryApi,
  SourceItemApi,
  SourceUsagePolicyApi,
  WorkspaceApi,
  WorkspaceSettingsApi,
  ConfirmationStateApi,
} from "@/api/apiTypes";
import type {
  AgentActionType,
  AgentCard,
  AgentMessage,
  DiagnosticSummary,
  ExportArtifact,
  FileType,
  ProductTypeOption,
  ReferenceStyleStrength,
  RunListItem,
  RunEventType,
  RunSummary,
  SourceItem,
  SourceType,
  WorkspaceAction,
  WorkspaceLastError,
  WorkspaceSettings,
  ConfirmationState,
  WorkspaceState,
  AllowedUsage,
  CorpusType,
  DocOutputType,
  ParseStatus,
} from "@/types/workspace";

export function mapWorkspace(payload: WorkspaceApi): WorkspaceState {
  return {
    runSummary: mapRunSummary(payload.run_summary),
    sources: payload.sources.map(mapSourceItem),
    exportArtifacts: payload.export_artifacts.map(mapExportArtifact),
    messages: payload.messages.map(mapAgentMessage),
    settings: mapWorkspaceSettings(payload.settings),
    confirmationState: payload.confirmation_state
      ? mapConfirmationState(payload.confirmation_state)
      : undefined,
    diagnostics: mapDiagnosticSummary(payload.diagnostics),
    availableActions: payload.available_actions.map(mapWorkspaceAction),
    primaryAction: payload.primary_action ? mapWorkspaceAction(payload.primary_action) : undefined,
    error: payload.error,
    lastError: payload.last_error ? mapLastError(payload.last_error) : null,
  };
}

export function mapRunListItem(payload: RunListItemApi): RunListItem {
  return {
    runId: payload.run_id,
    projectName: payload.project_name,
    taskName: payload.task_name,
    stageLabel: payload.stage_label,
    createdAt: payload.created_at,
    updatedAt: payload.updated_at,
  };
}

export function mapSourceItem(payload: SourceItemApi): SourceItem {
  return {
    sourceId: payload.source_id,
    runId: payload.run_id,
    sourceType: payload.source_type as SourceType,
    fileType: payload.file_type as FileType,
    corpusType: payload.corpus_type as CorpusType,
    allowedUsage: payload.allowed_usage as AllowedUsage,
    fileName: payload.file_name ?? "未命名资料",
    filePath: payload.file_path ?? undefined,
    fileSize: payload.file_size ?? undefined,
    uploadedAt: payload.uploaded_at,
    parseStatus: payload.parse_status as ParseStatus,
    parseError: payload.parse_error,
    statusLabel: payload.status_label,
    usagePolicy: mapSourceUsagePolicy(payload.usage_policy),
    notes: payload.notes ?? undefined,
    metadata: payload.metadata,
  };
}

function mapRunSummary(payload: RunSummaryApi): RunSummary {
  return {
    runId: payload.run_id,
    projectName: payload.project_name,
    taskName: payload.task_name,
    stageLabel: payload.stage_label,
    healthLabel: payload.health_label,
    healthTone: payload.health_tone,
  };
}

function mapSourceUsagePolicy(payload: SourceUsagePolicyApi) {
  return {
    label: payload.label,
    allowedUse: payload.allowed_use,
    riskBoundary: payload.risk_boundary,
    badgeType: payload.badge_type,
  };
}

function mapExportArtifact(payload: ExportArtifactApi): ExportArtifact {
  return {
    artifactId: payload.artifact_id,
    name: payload.name,
    type: payload.type,
    statusLabel: payload.status_label,
    downloadable: payload.downloadable,
  };
}

function mapWorkspaceAction(payload: AgentActionApi): WorkspaceAction {
  return {
    actionId: payload.action_id,
    actionType: payload.action_type as AgentActionType,
    label: payload.label,
    primary: payload.primary,
    disabled: payload.disabled,
    description: payload.description ?? undefined,
    payload: payload.payload,
  };
}

function mapWorkspaceSettings(payload: WorkspaceSettingsApi): WorkspaceSettings {
  return {
    productTypeHint: payload.product_type_hint as ProductTypeOption,
    docOutputType: payload.doc_output_type as DocOutputType,
    referenceStyleStrength: payload.reference_style_strength as ReferenceStyleStrength,
    strategyChangeMode: payload.strategy_change_mode,
  };
}

function mapConfirmationState(payload: ConfirmationStateApi): ConfirmationState {
  return {
    required: payload.required,
    autoConfirmed: payload.auto_confirmed,
    canAutoConfirm: payload.can_auto_confirm,
    reason: payload.reason,
    recommendedProductType: payload.recommended_product_type,
    userSelectedProductType: payload.user_selected_product_type,
    productTypeConflict: payload.product_type_conflict,
    recommendedDocType: payload.recommended_doc_type,
    selectedDocType: payload.selected_doc_type,
    referenceStyleStrength: payload.reference_style_strength,
    message: payload.message,
  };
}

function mapDiagnosticSummary(payload: DiagnosticSummaryApi): DiagnosticSummary {
  return {
    healthLabel: payload.health_label,
    stageLabel: payload.stage_label,
    nextSuggestion: payload.next_suggestion,
  };
}

function mapAgentMessage(payload: AgentMessageApi): AgentMessage {
  return {
    messageId: payload.message_id,
    runId: payload.run_id,
    role: payload.role,
    content: payload.content,
    createdAt: payload.created_at,
    createdAtLabel: payload.created_at_label,
    eventId: payload.event_id ?? undefined,
    eventType: payload.event_type as RunEventType | undefined,
    isUserVisible: payload.is_user_visible,
    card: payload.card ? (payload.card as unknown as AgentCard) : undefined,
  };
}

function mapLastError(payload: LastErrorApi): WorkspaceLastError {
  return {
    message: payload.message,
    occurredAt: payload.occurred_at,
    recoverable: payload.recoverable,
  };
}
