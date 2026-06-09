from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ApiErrorResponse(BaseModel):
    error_code: str
    message: str
    recoverable: bool = True
    suggested_action: str = ""


class RunSummaryView(BaseModel):
    run_id: str
    project_name: str
    task_name: str
    stage_label: str
    health_label: str
    health_tone: Literal["success", "warning", "danger", "info"] = "info"


class SourceUsagePolicyView(BaseModel):
    label: str
    allowed_use: str
    risk_boundary: str
    badge_type: Literal["info", "success", "warning"]


class SourceItemView(BaseModel):
    source_id: str
    run_id: str
    source_type: str
    file_type: str
    corpus_type: str
    allowed_usage: str
    file_name: str | None = None
    file_path: str | None = None
    file_size: int | None = None
    uploaded_at: str
    parse_status: str
    parse_error: str | None = None
    status_label: str
    usage_policy: SourceUsagePolicyView
    notes: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)


class ExportArtifactView(BaseModel):
    artifact_id: str
    name: str
    type: Literal["normal_docx", "risk_docx"]
    status_label: str
    downloadable: bool


class AgentActionView(BaseModel):
    action_id: str
    action_type: str
    label: str
    primary: bool
    disabled: bool
    description: str | None = None


class WorkspaceSettingsView(BaseModel):
    product_type_hint: str = "agent_decide"
    doc_output_type: str = "product_feature_description"
    reference_style_strength: str = "medium"


class DiagnosticIssueView(BaseModel):
    severity: str
    code: str
    message: str
    suggested_action: str = ""
    developer_detail: str | None = None


class SeverityCountsView(BaseModel):
    info: int = 0
    warning: int = 0
    error: int = 0


class DiagnosticSummaryView(BaseModel):
    health_label: str
    stage_label: str
    next_suggestion: str
    issues: list[DiagnosticIssueView] = Field(default_factory=list)
    severity_counts: SeverityCountsView = Field(default_factory=SeverityCountsView)


class AgentMessageView(BaseModel):
    message_id: str
    run_id: str
    role: Literal["user", "agent", "system"]
    content: str
    created_at: str
    created_at_label: str
    event_id: str | None = None
    event_type: str | None = None
    is_user_visible: bool = True


class LastErrorView(BaseModel):
    message: str
    occurred_at: str
    recoverable: bool = True


class WorkspaceView(BaseModel):
    run_summary: RunSummaryView
    sources: list[SourceItemView]
    export_artifacts: list[ExportArtifactView]
    messages: list[AgentMessageView]
    settings: WorkspaceSettingsView
    diagnostics: DiagnosticSummaryView
    available_actions: list[AgentActionView]
    primary_action: AgentActionView | None = None
    error: str | None = None
    last_error: LastErrorView | None = None


class ActionResultView(BaseModel):
    run_id: str
    success: bool
    message: str
    workspace: WorkspaceView | None = None


class ConfirmProductTypeRequest(BaseModel):
    selected_product_type: str
    use_agent_recommendation: bool = False
    reason: str | None = None


class ConfirmDocPlanRequest(BaseModel):
    accepted: bool = True
    note: str | None = None


class UploadNoteRequest(BaseModel):
    content: str


class FileUploadResult(BaseModel):
    source: SourceItemView


class ArtifactDownloadInfo(BaseModel):
    artifact_id: str
    file_name: str
    media_type: str = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

    model_config = ConfigDict(extra="forbid")

