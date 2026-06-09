import type {
  AgentActionType,
  AgentCardAction,
  AgentMessage,
  RunEventType,
  WorkspaceAction,
  WorkspaceState,
} from "@/types/workspace";

const RUN_ID = "mock-run-datatalk-001";

export const uploadMockAction: WorkspaceAction = {
  actionId: "action_open_upload_mock",
  actionType: "open_upload_mock",
  label: "上传资料",
  primary: false,
  disabled: false,
  description: "当前 Sprint 仅展示上传入口，真实文件上传将在后续 API 接入后实现。",
};

export const exportEntryMockAction: WorkspaceAction = {
  actionId: "action_export_entry_mock",
  actionType: "export_entry_mock",
  label: "导出入口",
  primary: false,
  disabled: false,
  description: "当前 Sprint 仅展示导出入口，真实 DOCX 下载将在后续 API 接入后实现。",
};

const primaryAction: WorkspaceAction = {
  actionId: "action_start_parse_sources",
  actionType: "start_parse_sources",
  label: "开始解析资料",
  primary: true,
  disabled: false,
  description: "解析资料并识别参考资料、自有资料和截图的用途边界。",
};

export const workspaceMock: WorkspaceState = {
  runSummary: {
    runId: RUN_ID,
    projectName: "DataTalk 软著文档生成",
    taskName: "当前运行任务：DataTalk 产品功能说明书",
    stageLabel: "资料已上传，等待解析",
    healthLabel: "正常，可继续",
    healthTone: "success",
  },
  sources: [
    {
      sourceId: "source-external-reference",
      runId: RUN_ID,
      sourceType: "reference_soft_copyright_doc",
      fileType: "pdf",
      corpusType: "reference_style",
      allowedUsage: "style_only",
      fileName: "中安智擎车辆动态...手册.pdf",
      fileSize: 8_734_720,
      uploadedAt: "2026-06-09T09:20:00+08:00",
      parseStatus: "saved",
      parseError: null,
      statusLabel: "已保存",
      usagePolicy: {
        label: "外部参考软著",
        allowedUse: "仅参考目录、章法、配图方式和语言风格",
        riskBoundary: "不能作为产品事实来源",
        badgeType: "warning",
      },
      notes: "外部参考资料只进入 reference_style 语料，不进入产品事实证据库。",
      metadata: {
        pageCount: 42,
        originalCategory: "reference_soft_copyright_doc",
      },
    },
    {
      sourceId: "source-own-product",
      runId: RUN_ID,
      sourceType: "product_intro_doc",
      fileType: "docx",
      corpusType: "product_evidence",
      allowedUsage: "factual_evidence",
      fileName: "DataTalk 产品介绍.docx",
      fileSize: 1_245_184,
      uploadedAt: "2026-06-09T09:22:00+08:00",
      parseStatus: "parsed",
      parseError: null,
      statusLabel: "已解析",
      usagePolicy: {
        label: "自有产品资料",
        allowedUse: "可用于产品能力描述和事实归纳",
        riskBoundary: "可以作为产品事实来源",
        badgeType: "success",
      },
      notes: "自有产品资料进入 product_evidence 语料，可用于产品能力和功能边界判断。",
      metadata: {
        paragraphCount: 128,
        productName: "DataTalk",
      },
    },
    {
      sourceId: "source-dashboard",
      runId: RUN_ID,
      sourceType: "screenshot",
      fileType: "png",
      corpusType: "product_evidence",
      allowedUsage: "display_material_only",
      fileName: "dashboard.png",
      fileSize: 684_032,
      uploadedAt: "2026-06-09T09:24:00+08:00",
      parseStatus: "saved",
      parseError: null,
      statusLabel: "已保存",
      usagePolicy: {
        label: "产品截图",
        allowedUse: "仅作为配图候选和展示材料登记",
        riskBoundary: "MVP 不做 OCR，不作为强产品事实证据，不用于推断当前版本已实现功能",
        badgeType: "info",
      },
      notes: "当前阶段截图仅作为配图候选和展示材料登记，MVP 不做 OCR，不作为强产品事实证据，不用于推断当前版本已实现功能。",
      metadata: {
        width: 1440,
        height: 900,
      },
    },
  ],
  exportArtifacts: [
    {
      artifactId: "export-normal",
      name: "正常版 DOCX",
      type: "normal_docx",
      statusLabel: "未生成",
      downloadable: false,
    },
    {
      artifactId: "export-risk",
      name: "风险版 DOCX",
      type: "risk_docx",
      statusLabel: "未生成",
      downloadable: false,
    },
  ],
  settings: {
    productTypeHint: "agent_decide",
    docOutputType: "product_feature_description",
    referenceStyleStrength: "medium",
  },
  diagnostics: {
    healthLabel: "正常，可继续",
    stageLabel: "资料已上传，等待解析",
    nextSuggestion: "开始解析资料",
  },
  availableActions: [uploadMockAction, primaryAction, exportEntryMockAction],
  primaryAction,
  error: null,
  lastError: null,
  messages: [
    createAgentTextMessage(
      "你好，我是墨衡 DocForge。请上传外部参考软著和自有产品资料，我会帮你完成资料归类、产品理解、文档计划、正文生成、风险检查和 DOCX 导出。",
      {
        messageId: "message-welcome",
        createdAt: "2026-06-09T09:30:00+08:00",
        eventType: "agent_message",
      },
    ),
    {
      ...createAgentTextMessage("我已完成资料登记，并先按证据边界做了归类。", {
        messageId: "message-source-card",
        createdAt: "2026-06-09T09:31:00+08:00",
        eventType: "source_received",
      }),
      card: {
        cardId: "card-source-received",
        cardType: "source_received",
        title: "Agent 已接收资料",
        summary: "资料已按用途边界完成 mock 归类。",
        counts: {
          externalReferences: 1,
          productMaterials: 1,
          screenshots: 1,
        },
        nextStepLabel: "解析资料并识别证据边界",
        actions: [
          cardAction("action_card_start_parse_sources", "start_parse_sources", "开始解析", "primary"),
        ],
      },
    },
    {
      ...createAgentTextMessage(
        "根据当前资料，我建议先确认产品边界，避免把参考文档能力误写成 DataTalk 的能力。",
        {
          messageId: "message-product-type-card",
          createdAt: "2026-06-09T09:32:00+08:00",
          eventType: "product_type_decision",
        },
      ),
      card: {
        cardId: "card-product-type",
        cardType: "product_type_decision",
        title: "产品类型判断",
        summary: "用户选择与 Agent 判断存在差异，需要二次确认。",
        userChoice: "AI 平台",
        agentJudgement: "AI 数据平台",
        recommendedType: "AI 数据平台",
        differenceReasons: [
          "资料中包含数据接入、治理、数据集管理",
          "资料中包含 AI 生成、智能分析能力",
          "AI 能力是核心能力之一，但不是唯一产品边界",
        ],
        actions: [
          cardAction(
            "action_use_agent_recommendation",
            "use_agent_recommendation",
            "按 Agent 推荐继续",
            "primary",
          ),
          cardAction("action_use_user_selection", "use_user_selection", "使用我的选择", "secondary"),
          cardAction(
            "action_view_difference_reason",
            "view_difference_reason",
            "查看差异原因",
            "secondary",
          ),
        ],
      },
    },
    {
      ...createAgentTextMessage(
        "软著文档目录已生成。确认后我会按该目录生成正文，不会擅自新增未被证据支持的产品能力。",
        {
          messageId: "message-doc-plan-card",
          createdAt: "2026-06-09T09:34:00+08:00",
          eventType: "doc_plan_confirm",
        },
      ),
      card: {
        cardId: "card-doc-plan",
        cardType: "doc_plan_confirm",
        title: "软著文档目录已生成",
        summary: "确认后进入正文生成前的计划质量检查。",
        sections: [
          "系统概述",
          "功能结构",
          "用户登录与权限管理",
          "数据接入管理",
          "数据集治理",
          "智能分析与生成",
          "系统配置与运维",
        ],
        actions: [
          cardAction("action_confirm_doc_plan", "confirm_doc_plan", "确认目录并生成正文", "primary"),
          cardAction("action_adjust_doc_plan", "adjust_doc_plan", "调整目录", "secondary"),
          cardAction("action_regenerate_doc_plan", "regenerate_doc_plan", "重新生成", "secondary"),
        ],
      },
    },
    {
      ...createAgentTextMessage("正文草稿已经完成，我对事实边界、参考风格和导出风险做了检查。", {
        messageId: "message-risk-card",
        createdAt: "2026-06-09T09:45:00+08:00",
        eventType: "risk_check_result",
      }),
      card: {
        cardId: "card-risk-check",
        cardType: "risk_check",
        title: "风险检查完成",
        summary: "当前不建议导出正常版 DOCX，建议导出风险版。",
        riskSummary: {
          blocker: 0,
          major: 2,
          minor: 5,
          suggestion: 3,
          conclusion: "当前不建议导出正常版 DOCX，建议导出风险版。",
        },
        actions: [
          cardAction("action_view_risk_detail", "view_risk_detail", "查看风险详情", "primary"),
          cardAction("action_export_risk_docx", "export_risk_docx", "导出风险版 DOCX", "secondary"),
          cardAction("action_return_to_revision", "return_to_revision", "返回修订", "secondary"),
        ],
      },
    },
    {
      ...createAgentTextMessage("风险版 DOCX 已生成，可下载后进入人工复核。", {
        messageId: "message-export-card",
        createdAt: "2026-06-09T09:48:00+08:00",
        eventType: "export_ready",
      }),
      card: {
        cardId: "card-export-result",
        cardType: "export_result",
        title: "文档已准备好",
        artifactName: "风险版 DOCX",
        description: "风险版 DOCX 已生成，可下载。",
        actions: [
          cardAction("action_download_risk_docx", "download_risk_docx", "下载风险版 DOCX", "primary"),
          cardAction(
            "action_view_generation_record",
            "view_generation_record",
            "查看生成记录",
            "secondary",
          ),
        ],
      },
    },
  ],
};

export function createAgentTextMessage(
  content: string,
  options: MessageFactoryOptions = {},
): AgentMessage {
  return createTextMessage("agent", content, options);
}

export function createUserTextMessage(
  content: string,
  options: MessageFactoryOptions = {},
): AgentMessage {
  return createTextMessage("user", content, options);
}

export function createSystemTextMessage(
  content: string,
  options: MessageFactoryOptions = {},
): AgentMessage {
  return createTextMessage("system", content, options);
}

function createTextMessage(
  role: AgentMessage["role"],
  content: string,
  options: MessageFactoryOptions,
): AgentMessage {
  const createdAt = options.createdAt ?? new Date().toISOString();

  return {
    messageId: options.messageId ?? crypto.randomUUID(),
    runId: options.runId ?? RUN_ID,
    role,
    content,
    createdAt,
    createdAtLabel: currentTimeLabel(createdAt),
    eventId: options.eventId,
    eventType: options.eventType,
    isUserVisible: options.isUserVisible ?? true,
  };
}

function cardAction(
  actionId: string,
  actionType: AgentActionType,
  label: string,
  variant: AgentCardAction["variant"],
  description?: string,
): AgentCardAction {
  return {
    actionId,
    actionType,
    label,
    variant,
    description,
  };
}

function currentTimeLabel(createdAt: string): string {
  return new Intl.DateTimeFormat("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(new Date(createdAt));
}

interface MessageFactoryOptions {
  messageId?: string;
  runId?: string;
  createdAt?: string;
  eventId?: string;
  eventType?: RunEventType;
  isUserVisible?: boolean;
}
