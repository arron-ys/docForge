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
      "当前版本仅支持明确指令，例如“开始”。补充产品事实请通过上传自有产品资料完成；这里的文字不会作为产品事实来源。",
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
    case "start":
    case "start_parse_sources":
      return "正在解析资料并构建证据。参考资料只用于目录、章法、配图方式和语言风格；产品截图仅作为配图候选，不作为事实证据。";
    case "use_agent_recommendation":
      return "已选择按 Agent 推荐继续。真实任务中会冻结当前确认结果，并继续进入后续正文生成前检查。";
    case "use_user_selection":
      return "已选择保留你的当前选择。真实任务中系统会保留人工确认来源，并继续进入后续正文生成前检查。";
    case "export-risk-docx":
      return "当前为界面演示数据，暂不生成真实 DOCX。真实任务中此按钮会触发风险版 DOCX 导出。";
    case "open_upload_mock":
      return "请在上传弹窗中选择资料类型和文件。产品文档只接受 docx/pdf/md/txt/html；截图仅作为展示材料，不做 OCR 和截图绑定。";
    case "export_entry_mock":
      return "真实 DOCX 下载需要先完成文档计划确认、正文生成和风险检查。";
    case "update_setting_mock":
      return "设置已更新。该设置用于当前页面的写作参考，推进主流程请在中间区域回复“开始”或“继续”。";
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
