import { httpClient } from "@/api/httpClient";
import { mapWorkspace } from "@/api/viewModelMapper";
import type { ActionResultApi } from "@/api/apiTypes";
import type { AgentCardAction, WorkspaceAction, WorkspaceState } from "@/types/workspace";

const WORKFLOW_ACTION_TIMEOUT_MS = 180_000;

const NEXT_ACTION_TYPES = new Set<string>([
  "parse_sources",
  "analyze_reference_style",
  "understand_product",
  "extract_evidence",
  "diagnose_software_type",
  "recommend_template",
  "freeze_doc_plan",
  "create_outline",
  "run_plan_quality_gate",
  "ask_missing_information",
  "write_draft",
  "plan_figure_slots",
  "audit_draft",
  "run_draft_quality_gate",
  "revise_draft",
  "audit_revised_draft",
  "start_parse_sources",
]);

const FINAL_EXPORT_ACTION_TYPES = new Set<string>([
  "export_docx",
  "export_final_doc",
  "export-final-docx",
]);

const RISK_EXPORT_ACTION_TYPES = new Set<string>([
  "export_risk_docx",
  "export_risk_doc",
  "export-risk-docx",
]);

const CONFIRM_ACTION_TYPES = new Set<string>([
  "ask_human_confirmation",
  "confirm_doc_plan",
  "confirm-doc-plan",
]);

export async function runWorkspaceAction(
  runId: string,
  action: AgentCardAction | WorkspaceAction,
): Promise<{ message: string; workspace: WorkspaceState | null }> {
  const endpoint = endpointForAction(action.actionType);
  const response = await httpClient.post<ActionResultApi>(
    `/runs/${encodeURIComponent(runId)}/actions/${endpoint}`,
    requestPayloadForEndpoint(endpoint, action),
    { timeout: WORKFLOW_ACTION_TIMEOUT_MS },
  );

  return {
    message: response.data.message,
    workspace: response.data.workspace ? mapWorkspace(response.data.workspace) : null,
  };
}

export async function runStartAction(
  runId: string,
): Promise<{ message: string; workspace: WorkspaceState | null }> {
  const response = await httpClient.post<ActionResultApi>(
    `/runs/${encodeURIComponent(runId)}/actions/start`,
    {},
    { timeout: WORKFLOW_ACTION_TIMEOUT_MS },
  );

  return {
    message: response.data.message,
    workspace: response.data.workspace ? mapWorkspace(response.data.workspace) : null,
  };
}

function endpointForAction(actionType: string): string {
  if (NEXT_ACTION_TYPES.has(actionType)) {
    return "next";
  }
  if (FINAL_EXPORT_ACTION_TYPES.has(actionType)) {
    return "export-final-docx";
  }
  if (RISK_EXPORT_ACTION_TYPES.has(actionType)) {
    return "export-risk-docx";
  }
  if (CONFIRM_ACTION_TYPES.has(actionType)) {
    return "confirm-doc-plan";
  }
  if (
    actionType === "confirm-product-type" ||
    actionType === "confirm_product_type" ||
    actionType === "use_agent_recommendation" ||
    actionType === "use_user_selection"
  ) {
    return "confirm-product-type";
  }
  if (actionType === "confirm_doc_plan" || actionType === "confirm-doc-plan") {
    return "confirm-doc-plan";
  }
  throw new Error("当前按钮尚未接入后端执行流程，请刷新工作台后选择当前可执行动作。");
}

function requestPayloadForEndpoint(
  endpoint: string,
  action: AgentCardAction | WorkspaceAction,
): Record<string, unknown> {
  if (action.payload) {
    return action.payload;
  }
  if (endpoint === "confirm-product-type") {
    return {
      selected_product_type: "agent_recommendation",
      use_agent_recommendation: true,
    };
  }
  if (endpoint === "confirm-doc-plan") {
    return { accepted: true };
  }
  return {};
}
