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
      "已记录为本页面备注。当前版本不会把这条内容提交给后端生成流程；请使用结构化按钮推进任务。",
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
      return "我会先解析资料，并检查参考资料与自有产品资料的用途边界。当前为界面演示数据，真实解析请切换到后端服务模式。";
    case "use_agent_recommendation":
      return "已选择按 Agent 推荐继续。真实任务中仍会结合自有产品资料和人工确认结果推进。";
    case "use_user_selection":
      return "已选择使用你的产品类型判断。真实任务中系统会保留差异原因，供人工确认时复核。";
    case "view_difference_reason":
      return "差异原因：资料中同时出现数据接入、数据集治理、AI 生成和智能分析能力，因此 Agent 倾向判断为 AI 数据平台，而不是单一 AI 平台。";
    case "confirm_doc_plan":
      return "已确认文档目录。真实任务中会锁定目录并进入正文生成前检查。";
    case "adjust_doc_plan":
      return "已记录目录调整意图。真实任务中会进入受控目录编辑，并保留生成前检查。";
    case "regenerate_doc_plan":
      return "已记录重新生成目录请求。真实任务中会触发受控重生成并重新等待确认。";
    case "view_risk_detail":
      return "当前 major 风险集中在部分能力描述过强和参考风格相似度偏高。Suggestion 仅作为优化建议，不阻塞导出。";
    case "export_risk_docx":
      return "当前为界面演示数据，暂不生成真实 DOCX。真实任务中此按钮会触发风险版 DOCX 导出。";
    case "return_to_revision":
      return "已记录返回修订意图。真实任务中会回到受控修订步骤，并保留风险检查上下文。";
    case "download_risk_docx":
      return "当前为界面演示数据，暂不下载真实 DOCX。真实任务中此按钮会下载风险版 DOCX。";
    case "view_generation_record":
      return "生成记录已模拟展示：正文生成、风险检查、风险版导出均已完成。真实任务中会返回实际记录。";
    case "open_upload_mock":
      return "请在上传弹窗中选择资料类型和文件。当前为界面演示数据，可先确认资料分类与用途边界。";
    case "export_entry_mock":
      return "真实 DOCX 下载需要先完成文档计划确认、正文生成和风险检查。";
    case "update_setting_mock":
      return "设置已更新。该设置用于当前页面的写作参考，实际推进仍需要使用当前主操作。";
    default: {
      return `当前界面演示暂未实现动作：${action.label}。真实推进请切换到后端服务模式并选择当前可执行动作。`;
    }
  }
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function clone<T>(value: T): T {
  return structuredClone(value);
}
