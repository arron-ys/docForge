export interface ApiErrorResponse {
  error_code: string;
  message: string;
  recoverable: boolean;
  suggested_action: string;
}

export interface RunSummaryApi {
  run_id: string;
  project_name: string;
  task_name: string;
  stage_label: string;
  health_label: string;
  health_tone: "success" | "warning" | "danger" | "info";
}

export interface RunListItemApi {
  run_id: string;
  project_name: string;
  task_name: string;
  stage_label: string;
  created_at: string;
  updated_at: string;
}

export interface RunListApi {
  runs: RunListItemApi[];
}

export interface CreateRunApi {
  run: RunListItemApi;
  workspace: WorkspaceApi;
}

export interface SourceUsagePolicyApi {
  label: string;
  allowed_use: string;
  risk_boundary: string;
  badge_type: "info" | "success" | "warning";
}

export interface SourceItemApi {
  source_id: string;
  run_id: string;
  source_type: string;
  file_type: string;
  corpus_type: string;
  allowed_usage: string;
  file_name: string | null;
  file_path: string | null;
  file_size: number | null;
  uploaded_at: string;
  parse_status: string;
  parse_error: string | null;
  status_label: string;
  usage_policy: SourceUsagePolicyApi;
  notes: string | null;
  metadata: Record<string, unknown>;
}

export interface ExportArtifactApi {
  artifact_id: string;
  name: string;
  type: "normal_docx" | "risk_docx";
  status_label: string;
  downloadable: boolean;
}

export interface AgentActionApi {
  action_id: string;
  action_type: string;
  label: string;
  primary: boolean;
  disabled: boolean;
  description: string | null;
}

export interface WorkspaceSettingsApi {
  product_type_hint: string;
  doc_output_type: string;
  reference_style_strength: string;
}

export interface DiagnosticIssueApi {
  severity: string;
  code: string;
  message: string;
  suggested_action: string;
  developer_detail: string | null;
}

export interface SeverityCountsApi {
  info: number;
  warning: number;
  error: number;
}

export interface DiagnosticSummaryApi {
  health_label: string;
  stage_label: string;
  next_suggestion: string;
  issues: DiagnosticIssueApi[];
  severity_counts: SeverityCountsApi;
}

export interface AgentMessageApi {
  message_id: string;
  run_id: string;
  role: "user" | "agent" | "system";
  content: string;
  created_at: string;
  created_at_label: string;
  event_id: string | null;
  event_type: string | null;
  is_user_visible: boolean;
}

export interface LastErrorApi {
  message: string;
  occurred_at: string;
  recoverable: boolean;
}

export interface WorkspaceApi {
  run_summary: RunSummaryApi;
  sources: SourceItemApi[];
  export_artifacts: ExportArtifactApi[];
  messages: AgentMessageApi[];
  settings: WorkspaceSettingsApi;
  diagnostics: DiagnosticSummaryApi;
  available_actions: AgentActionApi[];
  primary_action: AgentActionApi | null;
  error: string | null;
  last_error: LastErrorApi | null;
}

export interface FileUploadResultApi {
  source: SourceItemApi;
}

export interface ActionResultApi {
  run_id: string;
  success: boolean;
  message: string;
  workspace: WorkspaceApi | null;
}
