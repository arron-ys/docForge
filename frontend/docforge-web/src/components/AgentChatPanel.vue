<script setup lang="ts">
import { computed, nextTick, ref, watch } from "vue";
import { Promotion, Upload } from "@element-plus/icons-vue";

import MessageBubble from "@/components/MessageBubble.vue";
import type { AgentCardAction, AgentMessage, WorkspaceAction } from "@/types/workspace";

const props = defineProps<{
  messages: AgentMessage[];
  primaryAction?: WorkspaceAction;
  uploadAction?: WorkspaceAction;
  sending: boolean;
  apiKeyConfigured: boolean;
}>();

const emit = defineEmits<{
  "send-message": [content: string];
  "trigger-action": [action: AgentCardAction | WorkspaceAction];
}>();

const draft = ref("");
const scrollArea = ref<HTMLElement | null>(null);

const composerPlaceholder = computed(() => {
  if (props.sending) {
    return "正在执行，请稍候";
  }
  if (!props.apiKeyConfigured) {
    return "请先配置并测试模型密钥";
  }
  if (props.primaryAction?.actionType === "parse_sources") {
    return "回复“开始”以启动软著生成流程";
  }
  if (props.primaryAction?.actionType === "ask_human_confirmation") {
    return "请先确认产品类型和文档策略";
  }
  if (!props.primaryAction || props.primaryAction.disabled) {
    return "请先上传自有产品资料";
  }
  return "可输入“继续”执行当前主流程";
});

const primaryActionLabel = computed(() => {
  if (props.sending && props.primaryAction?.actionType === "parse_sources") {
    return "正在解析资料……";
  }
  return props.primaryAction ? `备用入口：${props.primaryAction.label}` : "暂无可执行动作";
});

const introInstruction = computed(() => {
  if (!props.apiKeyConfigured) {
    return "请先配置并测试模型密钥。系统会校验每一步，不能跳过必要流程。";
  }
  if (props.primaryAction?.actionType === "parse_sources") {
    return "上传自有产品资料后可回复“开始”。系统会校验每一步，不能跳过必要流程。";
  }
  if (props.primaryAction?.actionType === "ask_human_confirmation") {
    return "当前存在冲突或风险，请在确认卡片中明确选择后继续。";
  }
  if (props.primaryAction && !props.primaryAction.disabled) {
    return "当前可回复“继续”推进主流程，也可使用底部备用入口。";
  }
  return "请按当前提示补充资料或完成人工确认。系统会校验每一步。";
});

function submitMessage() {
  const content = draft.value.trim();
  if (!content || props.sending) {
    return;
  }

  emit("send-message", content);
  draft.value = "";
}

async function scrollToBottom() {
  await nextTick();
  if (scrollArea.value) {
    scrollArea.value.scrollTop = scrollArea.value.scrollHeight;
  }
}

watch(
  () => props.messages.length,
  () => {
    void scrollToBottom();
  },
  { immediate: true },
);
</script>

<template>
  <section class="chat-panel" aria-label="Agent 对话主窗口">
    <div ref="scrollArea" class="chat-panel__messages">
      <div class="chat-panel__intro">
        <span>Agent 工作区</span>
        <strong>{{ introInstruction }}</strong>
      </div>
      <MessageBubble
        v-for="message in messages"
        :key="message.messageId"
        :message="message"
        :busy="sending"
        @trigger-action="$emit('trigger-action', $event)"
      />
    </div>

    <footer class="chat-panel__composer">
      <div class="composer-toolbar">
        <el-tooltip :disabled="!uploadAction?.disabled" :content="uploadAction?.description">
          <el-button
            :icon="Upload"
            :disabled="sending || !uploadAction || uploadAction.disabled"
            @click="uploadAction && $emit('trigger-action', uploadAction)"
          >
            {{ uploadAction?.label ?? "上传资料" }}
          </el-button>
        </el-tooltip>
        <el-tooltip :disabled="!primaryAction?.disabled" :content="primaryAction?.description">
          <el-button
            type="primary"
            plain
            :loading="sending"
            :disabled="!primaryAction || primaryAction.disabled"
            @click="primaryAction && $emit('trigger-action', primaryAction)"
          >
            {{ primaryActionLabel }}
          </el-button>
        </el-tooltip>
      </div>
      <p v-if="!primaryAction || primaryAction.disabled" class="composer-state-hint">
        {{ primaryAction?.description ?? "当前没有可执行主操作。请先上传资料、刷新诊断，或等待后端完成上一阶段。" }}
      </p>
      <div class="composer-input">
        <span class="composer-input__label">受限指令入口</span>
        <el-input
          v-model="draft"
          :autosize="{ minRows: 2, maxRows: 3 }"
          type="textarea"
          resize="none"
          :placeholder="composerPlaceholder"
          @keydown.enter.exact.prevent="submitMessage"
        />
        <el-button
          type="primary"
          :icon="Promotion"
          :loading="sending"
          :disabled="sending || !draft.trim()"
          @click="submitMessage"
        >
          发送
        </el-button>
      </div>
    </footer>
  </section>
</template>

<style scoped>
.chat-panel {
  display: grid;
  grid-template-rows: minmax(0, 1fr) auto;
  height: 100%;
  overflow: hidden;
  background: var(--df-chat-bg);
}

.chat-panel__messages {
  min-height: 0;
  overflow-y: auto;
  padding: 22px clamp(20px, 3vw, 56px) 24px;
}

.chat-panel__intro {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  max-width: 840px;
  margin: 0 auto 16px;
  padding: 10px 14px;
  border: 1px solid var(--df-border);
  border-radius: var(--df-radius-lg);
  background: rgba(255, 255, 255, 0.72);
  color: var(--df-text-secondary);
  font-size: 12px;
}

.chat-panel__intro strong {
  color: var(--df-text);
  font-weight: 600;
}

.chat-panel__composer {
  padding: 12px clamp(20px, 3vw, 56px) 16px;
  border-top: 1px solid var(--df-border);
  background: rgba(255, 255, 255, 0.94);
  box-shadow: 0 -8px 24px rgba(31, 41, 55, 0.04);
}

.composer-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  max-width: 840px;
  margin: 0 auto 8px;
}

.composer-input {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: end;
  max-width: 840px;
  margin: 0 auto;
  gap: 10px;
}

.composer-input__label {
  grid-column: 1 / -1;
  color: var(--df-text-secondary);
  font-size: 12px;
  line-height: 1.4;
}

.composer-state-hint {
  max-width: 840px;
  margin: 0 auto 8px;
  color: var(--df-text-secondary);
  font-size: 12px;
  line-height: 1.5;
}

.composer-input :deep(.el-textarea__inner) {
  border-radius: var(--df-radius-lg);
  padding: 12px 14px;
  box-shadow: none;
}
</style>
