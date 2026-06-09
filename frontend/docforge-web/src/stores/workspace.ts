import { defineStore } from "pinia";

import { downloadArtifact as downloadArtifactApi } from "@/api/artifactApi";
import { DocForgeApiError, useMockApi } from "@/api/httpClient";
import { getWorkspaceState, sendUserMessage, triggerMockAction } from "@/api/mockClient";
import { runWorkspaceAction } from "@/api/runActionApi";
import { uploadSource, type SourceUploadType } from "@/api/sourceApi";
import { fetchWorkspace } from "@/api/workspaceApi";
import { createAgentTextMessage, createSystemTextMessage, createUserTextMessage } from "@/mock/workspaceMock";
import type {
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
              "已记录这条补充说明。自由文本只作为当前页面上下文提示；真实推进请继续使用结构化按钮并交由后端状态机校验。",
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

      if (isDownloadAction(action)) {
        const artifact = findDownloadArtifact(this.workspace.exportArtifacts, action.actionType);
        if (!artifact) {
          this.recordError(
            new Error("当前没有可下载的导出文件。请先完成文档生成和导出。"),
          );
          return;
        }
        await this.downloadArtifact(artifact);
        return;
      }

      if (action.actionType === "refresh_diagnostics") {
        await this.refreshWorkspace();
        this.appendSystemMessage("诊断信息已刷新。");
        return;
      }

      this.actionRunning = true;
      this.workspace.messages.push(
        createUserTextMessage(`已选择：${action.label}`, {
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
          this.appendSystemMessage(`Mock 模式已模拟上传：${file.name}。`);
        } else {
          await uploadSource(this.runId, uploadType, file);
          await this.refreshWorkspace();
          this.appendSystemMessage("资料已上传并登记。");
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
          this.appendSystemMessage("Mock 模式暂不下载真实 DOCX。");
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
          `${source.usagePolicy.label}「${source.fileName}」的用途边界：${source.usagePolicy.allowedUse}；${source.usagePolicy.riskBoundary}。`,
          { runId: this.workspace.runSummary.runId, eventType: "system_notice" },
        ),
      );
    },

    updateProductTypeHint(value: ProductTypeOption) {
      if (!this.workspace || this.workspace.settings.productTypeHint === value) {
        return;
      }

      this.workspace.settings.productTypeHint = value;
      this.appendSettingMessage(
        `已更新产品类型提示：${productTypeLabel(value)}。该选择只作为 Agent 的 prior_hint，不会直接锁死判断。若 Agent 判断与用户选择冲突，系统会展示差异原因并要求二次确认。`,
      );
    },

    updateDocOutputType(value: DocOutputType) {
      if (!this.workspace || this.workspace.settings.docOutputType === value) {
        return;
      }

      this.workspace.settings.docOutputType = value;
      this.appendSettingMessage(
        `已更新输出文档类型：${docOutputTypeLabel(value)}。该选择会作为输出约束，后续真实推进仍必须通过 FastAPI Action API 和后端状态机。`,
      );
    },

    updateReferenceStyleStrength(value: ReferenceStyleStrength) {
      if (!this.workspace || this.workspace.settings.referenceStyleStrength === value) {
        return;
      }

      this.workspace.settings.referenceStyleStrength = value;
      this.appendSettingMessage(
        `已更新参考风格强度：${referenceStyleStrengthLabel(value)}。外部参考软著仍只能影响目录结构、章法、配图方式和语言风格，不能作为产品事实来源。`,
      );
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

function isDownloadAction(action: AgentCardAction | WorkspaceAction): boolean {
  return action.actionType === "download_risk_docx";
}

function findDownloadArtifact(
  artifacts: ExportArtifact[],
  actionType: string,
): ExportArtifact | null {
  if (actionType === "download_risk_docx") {
    return artifacts.find((artifact) => artifact.type === "risk_docx" && artifact.downloadable) ?? null;
  }
  return artifacts.find((artifact) => artifact.downloadable) ?? null;
}

function mergeWorkspaceMessages(
  workspace: WorkspaceState,
  messagesToAppend: AgentMessage[],
): WorkspaceState {
  return {
    ...workspace,
    messages: [...workspace.messages, ...messagesToAppend],
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
        message: actionNotAllowedMessage(error.message),
        recoverable: error.recoverable,
        suggestedAction: actionNotAllowedSuggestion(error.message, error.suggestedAction),
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
        suggestedAction: error.suggestedAction || "请确认 FastAPI 使用的 data_dir，并重新选择任务。",
      };
    }
    if (error.errorCode === "upload_file_type_not_allowed") {
      return {
        message: error.message,
        recoverable: error.recoverable,
        suggestedAction:
          error.suggestedAction ||
          "请确认上传类型与文件扩展名匹配：文档类使用 docx/pdf/md/txt/html，截图使用 png/jpg/jpeg/webp。",
      };
    }
    if (error.errorCode === "network_error") {
      return {
        message: "无法连接 DocForge API，请确认 FastAPI 服务已启动。",
        recoverable: true,
        suggestedAction: "启动 python -m uvicorn api.main:app --reload 后重试。",
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

function actionNotAllowedMessage(rawMessage: string): string {
  if (rawMessage.includes("已预留") || rawMessage.includes("后续 Sprint")) {
    return "该确认动作后端接口已预留，完整确认流程将在后续 Sprint 接入。";
  }
  return "当前状态还不能执行该操作，请先完成上一阶段。";
}

function actionNotAllowedSuggestion(rawMessage: string, fallback: string): string {
  if (rawMessage.includes("已预留") || rawMessage.includes("后续 Sprint")) {
    return "请继续使用当前可执行的主操作，或等待确认流程接入后再提交该动作。";
  }
  return fallback || "刷新工作台后重新选择当前可执行动作。";
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
