import { defineStore } from "pinia";
import { ElMessageBox } from "element-plus";

import { downloadArtifact as downloadArtifactApi } from "@/api/artifactApi";
import { DocForgeApiError, useMockApi } from "@/api/httpClient";
import { getWorkspaceState, sendUserMessage, triggerMockAction } from "@/api/mockClient";
import { runStartAction, runWorkspaceAction } from "@/api/runActionApi";
import { saveRunSettings } from "@/api/runSettingsApi";
import { createRun, listRuns } from "@/api/runsApi";
import { uploadSource, type SourceUploadType } from "@/api/sourceApi";
import { fetchWorkspace } from "@/api/workspaceApi";
import { createAgentTextMessage, createSystemTextMessage, createUserTextMessage } from "@/mock/workspaceMock";
import type {
  AllowedUsage,
  AgentCardAction,
  AgentMessage,
  DocOutputType,
  ExportArtifact,
  ProductTypeOption,
  ReferenceStyleStrength,
  SourceItem,
  WorkspaceAction,
  WorkspaceLastError,
  WorkspaceState,
} from "@/types/workspace";

interface WorkspaceStoreState {
  workspace: WorkspaceState | null;
  loading: boolean;
  sending: boolean;
  uploading: boolean;
  actionRunning: boolean;
  downloadingArtifactId: string | null;
  runId: string | null;
  emptyReason: string | null;
}

export const useWorkspaceStore = defineStore("workspace", {
  state: (): WorkspaceStoreState => ({
    workspace: null,
    loading: false,
    sending: false,
    uploading: false,
    actionRunning: false,
    downloadingArtifactId: null,
    runId: null,
    emptyReason: null,
  }),

  getters: {
    messages(state): AgentMessage[] {
      return state.workspace?.messages ?? [];
    },
    isBusy(state): boolean {
      return state.loading || state.sending || state.uploading || state.actionRunning;
    },
  },

  actions: {
    async loadInitialWorkspace(runId?: string | null): Promise<string | null> {
      const requestedRunId = runId?.trim() || null;
      if (requestedRunId || useMockApi) {
        await this.loadWorkspace(requestedRunId);
        return this.runId;
      }

      this.loading = true;
      this.emptyReason = null;
      this.runId = null;
      try {
        const runs = await listRuns();
        if (runs.length > 0) {
          const latestRunId = runs[0].runId;
          this.workspace = await fetchWorkspace(latestRunId);
          this.runId = latestRunId;
        } else {
          const result = await createRun();
          this.workspace = result.workspace;
          this.runId = result.run.runId;
        }
        this.clearError();
        return this.runId;
      } catch (error) {
        this.workspace = null;
        this.recordError(error);
        return null;
      } finally {
        this.loading = false;
      }
    },

    async loadWorkspace(runId?: string | null) {
      const requestedRunId = runId?.trim() || null;
      this.runId = requestedRunId;

      if (!useMockApi && !requestedRunId) {
        this.workspace = null;
        this.emptyReason = "请先选择或创建任务。";
        return;
      }

      this.loading = true;
      this.emptyReason = null;
      try {
        this.workspace = useMockApi
          ? await getWorkspaceState()
          : await fetchWorkspace(requestedRunId as string);
        this.runId = this.workspace.runSummary.runId;
        this.clearError();
      } catch (error) {
        this.recordError(error);
      } finally {
        this.loading = false;
      }
    },

    async refreshWorkspace() {
      if (!this.runId) {
        return;
      }
      await this.loadWorkspace(this.runId);
    },

    async sendMessage(content: string) {
      const trimmed = content.trim();
      if (!trimmed || !this.workspace || this.sending) {
        return;
      }

      if (isStartCommand(trimmed)) {
        if (
          this.workspace.confirmationState?.required &&
          !this.workspace.confirmationState.canAutoConfirm
        ) {
          this.appendAgentMessage(
            "当前存在需要人工确认的产品类型和文档策略，请先在确认卡片中选择后再继续。",
            "system_notice",
          );
          return;
        }
        this.workspace.messages.push(
          createUserTextMessage(trimmed, {
            runId: this.workspace.runSummary.runId,
            eventType: "user_message",
          }),
        );
        await this.startMainFlow();
        return;
      }

      this.sending = true;
      try {
        if (useMockApi) {
          const messages = await sendUserMessage(trimmed);
          this.workspace.messages.push(...messages);
        } else {
          this.workspace.messages.push(
            createUserTextMessage(trimmed, {
              runId: this.workspace.runSummary.runId,
              eventType: "user_message",
            }),
          );
          this.workspace.messages.push(
            createAgentTextMessage(
              "当前版本仅支持明确指令，例如“开始”。补充产品事实请通过上传自有产品资料完成；这里的文字不会作为产品事实来源。",
              {
                runId: this.workspace.runSummary.runId,
                eventType: "system_notice",
              },
            ),
          );
        }
        this.clearError();
      } catch (error) {
        this.recordError(error);
      } finally {
        this.sending = false;
      }
    },

    async triggerAction(action: AgentCardAction | WorkspaceAction) {
      if (!this.workspace || this.actionRunning || action.disabled) {
        return;
      }

      if (isUploadAction(action)) {
        this.appendSystemMessage("请在上传弹窗中选择资料类型和文件。");
        return;
      }

      if (action.actionType === "refresh_diagnostics") {
        await this.refreshWorkspace();
        this.appendSystemMessage("诊断信息已刷新。");
        return;
      }

      if (isStartFlowAction(action)) {
        this.workspace.messages.push(
          createUserTextMessage(`你选择了：${action.label}`, {
            runId: this.workspace.runSummary.runId,
            eventType: "action_triggered",
          }),
        );
        await this.startMainFlow();
        return;
      }

      this.actionRunning = true;
      this.workspace.messages.push(
        createUserTextMessage(`你选择了：${action.label}`, {
          runId: this.workspace.runSummary.runId,
          eventType: "action_triggered",
        }),
      );

      try {
        if (useMockApi) {
          const messages = await triggerMockAction(action);
          this.workspace.messages.push(...messages);
        } else {
          const result = await runWorkspaceAction(this.workspace.runSummary.runId, action);
          if (result.workspace) {
            this.workspace = mergeWorkspaceMessages(result.workspace, [
              createAgentTextMessage(result.message, {
                runId: result.workspace.runSummary.runId,
                eventType: "action_triggered",
              }),
            ]);
          } else {
            this.appendSystemMessage(result.message);
          }
        }
        this.clearError();
      } catch (error) {
        this.recordError(error);
      } finally {
        this.actionRunning = false;
      }
    },

    async uploadSourceFile(uploadType: SourceUploadType, file: File): Promise<boolean> {
      if (this.uploading) {
        return false;
      }
      if (!this.workspace || !this.runId) {
        this.recordError(new Error("请先选择任务。"));
        return false;
      }

      this.uploading = true;
      try {
        if (useMockApi) {
          this.appendSystemMessage(`已在界面演示中记录上传：${file.name}。`);
        } else {
          await uploadSource(this.runId, uploadType, file);
          await this.refreshWorkspace();
          this.appendSystemMessage("资料已上传。");
        }
        this.clearError();
        return true;
      } catch (error) {
        this.recordError(error);
        return false;
      } finally {
        this.uploading = false;
      }
    },

    async startMainFlow() {
      if (!this.workspace || !this.runId || this.actionRunning) {
        return;
      }
      if (
        this.workspace.confirmationState?.required &&
        !this.workspace.confirmationState.canAutoConfirm
      ) {
        this.appendAgentMessage(
          "请先在确认卡片中选择采用系统推荐或保留你的选择，不能用“继续”绕过确认。",
          "system_notice",
        );
        return;
      }

      this.actionRunning = true;
      this.markPendingSourcesParsing();
      this.appendAgentMessage(this.currentWorkflowProgressMessage(), "action_triggered");

      try {
        if (useMockApi) {
          const messages = await triggerMockAction({
            actionId: "action_start",
            actionType: "start",
            label: "开始",
            primary: true,
            disabled: false,
          });
          this.workspace.messages.push(...messages);
          this.markParsingSourcesParsed();
        } else {
          const primaryAction = this.workspace.primaryAction;
          let result;
          if (
            this.workspace.confirmationState?.required &&
            this.workspace.confirmationState.canAutoConfirm
          ) {
            result = await runStartAction(this.runId);
          } else if (primaryAction?.actionType === "ask_human_confirmation") {
            result = await runWorkspaceAction(this.runId, primaryAction);
          } else {
            result = await runStartAction(this.runId);
          }
          if (result.workspace) {
            this.workspace = mergeWorkspaceMessages(result.workspace, [
              createAgentTextMessage(result.message, {
                runId: result.workspace.runSummary.runId,
                eventType: "action_triggered",
              }),
            ]);
          } else {
            this.appendSystemMessage(result.message);
          }
        }
        this.clearError();
      } catch (error) {
        if (!useMockApi) {
          await this.refreshWorkspace();
        }
        this.recordError(error);
      } finally {
        this.actionRunning = false;
      }
    },

    markPendingSourcesParsing() {
      if (!this.workspace) {
        return;
      }
      this.workspace.sources = this.workspace.sources.map((source) =>
        source.parseStatus === "pending" || source.parseStatus === "saved"
          ? { ...source, parseStatus: "parsing" }
          : source,
      );
    },

    currentWorkflowProgressMessage(): string {
      const actionType = this.workspace?.primaryAction?.actionType;
      const actionLabel = this.workspace?.primaryAction?.label;

      if (actionType === "parse_sources" || actionType === "start_parse_sources") {
        return "正在解析资料并构建证据……";
      }
      if (actionType === "ask_human_confirmation") {
        return "正在确认产品类型和文档策略……";
      }
      if (actionLabel) {
        return `正在执行：${actionLabel}……`;
      }
      return "正在推进当前主流程……";
    },

    markParsingSourcesParsed() {
      if (!this.workspace) {
        return;
      }
      this.workspace.sources = this.workspace.sources.map((source) =>
        source.parseStatus === "parsing" || source.parseStatus === "embedding"
          ? { ...source, parseStatus: "parsed" }
          : source,
      );
    },

    async downloadArtifact(artifact: ExportArtifact) {
      if (!artifact.downloadable || this.downloadingArtifactId) {
        if (!artifact.downloadable) {
          this.recordError(new Error("导出文件不存在或尚未生成。"));
        }
        return;
      }

      this.downloadingArtifactId = artifact.artifactId;
      try {
        if (useMockApi) {
          this.appendSystemMessage("当前为界面演示数据，暂不下载真实 DOCX。");
        } else {
          await downloadArtifactApi(artifact.artifactId);
          this.appendSystemMessage(`已开始下载：${downloadFileName(artifact)}。`);
        }
        this.clearError();
      } catch (error) {
        this.recordError(error);
      } finally {
        this.downloadingArtifactId = null;
      }
    },

    explainSource(source: SourceItem) {
      if (!this.workspace) {
        return;
      }

      this.workspace.messages.push(
        createAgentTextMessage(
          `${sourceUsageLabel(source.allowedUsage)}「${source.fileName}」的用途边界：${sourceUsageAllowedUse(source.allowedUsage)}；${sourceUsageRiskBoundary(source.allowedUsage)}。`,
          { runId: this.workspace.runSummary.runId, eventType: "system_notice" },
        ),
      );
    },

    async updateProductTypeHint(value: ProductTypeOption) {
      if (!this.workspace || this.workspace.settings.productTypeHint === value) {
        return;
      }
      await this.updateCriticalSetting(
        { productTypeHint: value },
        `已更新产品类型判断参考：${productTypeLabel(value)}。`,
      );
    },

    async updateDocOutputType(value: DocOutputType) {
      if (!this.workspace || this.workspace.settings.docOutputType === value) {
        return;
      }
      await this.updateCriticalSetting(
        { docOutputType: value },
        `已更新输出文档类型：${docOutputTypeLabel(value)}。`,
      );
    },

    async updateReferenceStyleStrength(value: ReferenceStyleStrength) {
      if (!this.workspace || this.workspace.settings.referenceStyleStrength === value) {
        return;
      }
      await this.updateCriticalSetting(
        { referenceStyleStrength: value },
        `已更新参考风格强度：${referenceStyleStrengthLabel(value)}。外部参考资料仍不能作为产品事实来源。`,
      );
    },

    async updateCriticalSetting(
      patch: Partial<Pick<WorkspaceState["settings"], "productTypeHint" | "docOutputType" | "referenceStyleStrength">>,
      successMessage: string,
    ) {
      if (!this.workspace || !this.runId || this.actionRunning) {
        return;
      }

      const mode = this.workspace.settings.strategyChangeMode;
      try {
        if (mode === "reevaluate") {
          await ElMessageBox.confirm(
            "修改关键策略会触发系统重新评估产品类型和文档策略。是否继续？",
            "重新评估策略",
            { confirmButtonText: "继续修改", cancelButtonText: "取消", type: "warning" },
          );
        } else if (mode === "restart") {
          await ElMessageBox.confirm(
            "当前文档策略已确认。修改会终止当前生成流程并重新评估；已上传资料和模型密钥会保留，草稿、风险检查和导出产物可能失效。是否继续？",
            "确认修改并重新开始",
            { confirmButtonText: "确认修改并重新开始", cancelButtonText: "取消", type: "warning" },
          );
        }
      } catch (error) {
        if (error === "cancel" || error === "close") {
          return;
        }
        this.recordError(error);
        return;
      }

      const nextSettings = { ...this.workspace.settings, ...patch };
      this.actionRunning = true;
      try {
        if (useMockApi) {
          this.workspace.settings = nextSettings;
        } else {
          const result = await saveRunSettings(this.runId, nextSettings, mode === "restart");
          if (result.workspace) {
            this.workspace = result.workspace;
          }
        }
        this.appendSettingMessage(successMessage);
        this.clearError();
      } catch (error) {
        this.recordError(error);
      } finally {
        this.actionRunning = false;
      }
    },

    appendSettingMessage(content: string) {
      this.appendAgentMessage(content, "setting_updated");
    },

    appendSystemMessage(content: string) {
      if (!this.workspace) {
        return;
      }

      this.workspace.messages.push(
        createSystemTextMessage(content, {
          runId: this.workspace.runSummary.runId,
          eventType: "system_notice",
        }),
      );
    },

    appendAgentMessage(content: string, eventType: AgentMessage["eventType"]) {
      if (!this.workspace) {
        return;
      }

      this.workspace.messages.push(
        createAgentTextMessage(content, {
          runId: this.workspace.runSummary.runId,
          eventType,
        }),
      );
    },

    recordError(error: unknown) {
      const apiError = normalizeError(error);
      const lastError: WorkspaceLastError = {
        message: apiError.message,
        occurredAt: new Date().toISOString(),
        recoverable: apiError.recoverable,
      };
      const userMessage = apiError.suggestedAction
        ? `${apiError.message} ${apiError.suggestedAction}`
        : apiError.message;

      if (!this.workspace) {
        this.emptyReason = userMessage;
        return;
      }

      this.workspace.error = userMessage;
      this.workspace.lastError = lastError;
      this.workspace.messages.push(
        createSystemTextMessage(userMessage, {
          runId: this.workspace.runSummary.runId,
          eventType: "error",
        }),
      );
    },

    clearError() {
      if (!this.workspace) {
        return;
      }

      this.workspace.error = null;
    },
  },
});

function isUploadAction(action: AgentCardAction | WorkspaceAction): boolean {
  return action.actionType === "open_upload" || action.actionType === "open_upload_mock";
}

function isStartFlowAction(action: AgentCardAction | WorkspaceAction): boolean {
  return (
    action.actionType === "start" ||
    action.actionType === "parse_sources" ||
    action.actionType === "start_parse_sources" ||
    action.actionType === "ask_human_confirmation"
  );
}

function isStartCommand(content: string): boolean {
  return ["开始", "开始写作", "开始生成", "继续"].includes(content.trim());
}

function mergeWorkspaceMessages(
  workspace: WorkspaceState,
  messagesToAppend: AgentMessage[],
): WorkspaceState {
  const existingContents = new Set(workspace.messages.map((message) => message.content));
  return {
    ...workspace,
    messages: [
      ...workspace.messages,
      ...messagesToAppend.filter((message) => !existingContents.has(message.content)),
    ],
  };
}

function normalizeError(error: unknown): {
  message: string;
  recoverable: boolean;
  suggestedAction: string;
} {
  if (error instanceof DocForgeApiError) {
    if (error.errorCode === "action_not_allowed") {
      return {
        message: error.message || "当前状态还不能执行该操作。",
        recoverable: error.recoverable,
        suggestedAction: error.suggestedAction || "刷新工作台后重新选择当前可执行动作。",
      };
    }
    if (error.errorCode === "artifact_not_found") {
      return {
        message: "导出文件不存在或尚未生成。",
        recoverable: error.recoverable,
        suggestedAction: error.suggestedAction || "请先完成正文生成、风险检查和对应导出动作。",
      };
    }
    if (error.errorCode === "invalid_run_id") {
      return {
        message: "任务编号格式非法，系统已拒绝访问。",
        recoverable: error.recoverable,
        suggestedAction: error.suggestedAction || "请返回工作台并重新选择任务。",
      };
    }
    if (error.errorCode === "state_not_found") {
      return {
        message: "任务状态文件不存在，可能是任务尚未创建或数据目录不一致。",
        recoverable: error.recoverable,
        suggestedAction: error.suggestedAction || "请确认后端服务使用的数据目录，并重新选择任务。",
      };
    }
    if (error.errorCode === "upload_file_type_not_allowed") {
      return {
        message: error.message,
        recoverable: error.recoverable,
        suggestedAction:
          error.suggestedAction ||
          "请确认上传类型与文件格式匹配：外部参考资料使用文档类文件；自有产品资料可选择产品文档或产品截图。",
      };
    }
    if (error.errorCode === "network_error") {
      return {
        message: error.message || "无法连接 DocForge API，请确认后端服务已启动。",
        recoverable: true,
        suggestedAction:
          error.suggestedAction || "确认 http://127.0.0.1:8000/healthz 可访问后重试。",
      };
    }
    if (error.errorCode === "request_timeout") {
      return {
        message: error.message,
        recoverable: true,
        suggestedAction: error.suggestedAction,
      };
    }
    if (
      [
        "workflow_dependency_missing",
        "model_config_missing",
        "model_connection_failed",
        "source_missing",
        "source_parse_failed",
        "product_evidence_missing",
        "screenshot_only_not_allowed",
        "reference_only_not_allowed",
        "backend_internal_error",
      ].includes(error.errorCode)
    ) {
      return {
        message: error.message,
        recoverable: error.recoverable,
        suggestedAction: error.suggestedAction,
      };
    }
    return {
      message: error.message,
      recoverable: error.recoverable,
      suggestedAction: error.suggestedAction,
    };
  }

  if (error instanceof Error) {
    return {
      message: error.message,
      recoverable: true,
      suggestedAction: "请刷新工作台或重新选择可执行动作。",
    };
  }

  return {
    message: "当前操作暂不可用。",
    recoverable: true,
    suggestedAction: "请刷新工作台或重新选择可执行动作。",
  };
}

function downloadFileName(artifact: ExportArtifact): string {
  if (artifact.name.toLowerCase().endsWith(".docx")) {
    return artifact.name;
  }
  return `${artifact.name}.docx`;
}

function productTypeLabel(value: ProductTypeOption): string {
  const labels: Record<ProductTypeOption, string> = {
    saas_web_platform: "SaaS / Web 平台",
    ai_platform: "AI 平台",
    data_platform: "数据平台",
    industrial_software: "工业软件",
    tool_software: "工具软件",
    agent_decide: "让 Agent 根据资料判断",
  };

  return labels[value];
}

function docOutputTypeLabel(value: DocOutputType): string {
  const labels: Record<DocOutputType, string> = {
    user_manual: "用户操作手册型软著",
    product_feature_description: "产品功能说明型软著",
    technical_design: "技术设计说明型软著",
  };

  return labels[value];
}

function referenceStyleStrengthLabel(value: ReferenceStyleStrength): string {
  const labels: Record<ReferenceStyleStrength, string> = {
    weak: "弱参考",
    medium: "中参考",
    strong: "强参考",
  };

  return labels[value];
}

function sourceUsageLabel(value: AllowedUsage): string {
  const labels: Record<AllowedUsage, string> = {
    style_only: "外部参考资料",
    factual_evidence: "自有产品资料",
    display_material_only: "产品截图",
  };

  return labels[value];
}

function sourceUsageAllowedUse(value: AllowedUsage): string {
  const labels: Record<AllowedUsage, string> = {
    style_only: "仅参考目录、章法、配图方式和语言风格",
    factual_evidence: "可作为产品事实依据",
    display_material_only: "仅用于配图和展示",
  };

  return labels[value];
}

function sourceUsageRiskBoundary(value: AllowedUsage): string {
  const labels: Record<AllowedUsage, string> = {
    style_only: "不能作为产品事实来源",
    factual_evidence: "系统会基于证据提取能力、状态和置信度使用",
    display_material_only: "不做 OCR，不作为产品事实证据",
  };

  return labels[value];
}
