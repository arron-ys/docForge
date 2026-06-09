import {
  createAgentTextMessage,
  createUserTextMessage,
  workspaceMock,
} from "@/mock/workspaceMock";
import type { AgentCardAction, AgentMessage, WorkspaceAction, WorkspaceState } from "@/types/workspace";

const MOCK_DELAY_MS = 180;

export class MockActionError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "MockActionError";
  }
}

export async function getWorkspaceState(): Promise<WorkspaceState> {
  await delay(MOCK_DELAY_MS);
  return clone(workspaceMock);
}

export async function sendUserMessage(content: string): Promise<AgentMessage[]> {
  await delay(MOCK_DELAY_MS);
  return [
    createUserTextMessage(content, { eventType: "user_message" }),
    createAgentTextMessage(
      "已收到你的补充说明。Mock 模式会把这条信息视为 Agent 工作流上下文演示，不调用真实后端。",
      { eventType: "agent_message" },
    ),
  ];
}

export async function triggerMockAction(
  action: AgentCardAction | WorkspaceAction,
): Promise<AgentMessage[]> {
  await delay(MOCK_DELAY_MS);
  const reply = mockActionReply(action);

  return [createAgentTextMessage(reply, { eventType: "action_triggered" })];
}

function mockActionReply(action: AgentCardAction | WorkspaceAction): string {
  switch (action.actionType) {
    case "start_parse_sources":
      return "我会先解析资料，并检查参考资料与自有产品资料的用途边界。当前 Sprint 仍是 mock 模式，真实解析将在后续 API 接入后完成。";
    case "use_agent_recommendation":
      return "已选择按 Agent 推荐继续。后续会将该选择提交给后端 HumanConfirmGate，并由状态机校验后推进。";
    case "use_user_selection":
      return "已选择使用你的产品类型判断。后续接入真实后端后，系统会将该选择作为人工覆盖意见，但仍会保留 Agent 差异原因。";
    case "view_difference_reason":
      return "差异原因：资料中同时出现数据接入、数据集治理、AI 生成和智能分析能力，因此 Agent 倾向判断为 AI 数据平台，而不是单一 AI 平台。";
    case "confirm_doc_plan":
      return "已确认文档目录。后续真实流程中，后端会冻结 FrozenDocPlan，并进入 PlanQualityGate。";
    case "adjust_doc_plan":
      return "已记录目录调整意图。后续真实流程中会进入受控目录编辑，不会直接绕过计划质量检查。";
    case "regenerate_doc_plan":
      return "已记录重新生成目录请求。后续接入真实后端后，这里会触发受控重生成并重新等待确认。";
    case "view_risk_detail":
      return "当前 major 风险集中在部分能力描述过强和参考风格相似度偏高。Suggestion 仅作为优化建议，不阻塞导出。";
    case "export_risk_docx":
      return "当前为 mock 模式，暂不生成真实 DOCX。后续接入 Artifact API 后，此按钮会触发风险版 DOCX 导出。";
    case "return_to_revision":
      return "已记录返回修订意图。正式工作流中会回到受控修订步骤，并保留风险检查上下文。";
    case "download_risk_docx":
      return "当前为 mock 模式，暂不下载真实 DOCX。后续接入 Artifact Download API 后，此按钮会下载风险版 DOCX。";
    case "view_generation_record":
      return "生成记录已模拟展示：正文生成、风险检查、风险版导出均已完成 mock 流程。后续会由 Artifact API 返回真实记录。";
    case "open_upload_mock":
      return "当前 Sprint 仅展示上传入口，真实文件上传将在 FastAPI Source Upload API 接入后实现。你可以先查看左侧 mock 资料区，确认资料分类与用途边界。";
    case "export_entry_mock":
      return "当前 Sprint 仅展示导出入口，真实 DOCX 下载将在 Artifact Download API 接入后实现。请先完成文档计划确认、正文生成和风险检查。";
    case "update_setting_mock":
      return "设置已更新。该设置会作为 Agent prior_hint 或输出约束，不会直接绕过后端状态机。";
    default: {
      return `Mock 模式暂未实现动作：${action.label}。真实推进请切换到 API 模式并通过后端 ActionGuard 执行。`;
    }
  }
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function clone<T>(value: T): T {
  return structuredClone(value);
}
