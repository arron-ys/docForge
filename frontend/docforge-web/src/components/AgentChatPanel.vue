<script setup lang="ts">
import { nextTick, ref, watch } from "vue";
import { Promotion, Upload } from "@element-plus/icons-vue";

import MessageBubble from "@/components/MessageBubble.vue";
import type { AgentCardAction, AgentMessage, WorkspaceAction } from "@/types/workspace";

const props = defineProps<{
  messages: AgentMessage[];
  primaryAction?: WorkspaceAction;
  uploadAction?: WorkspaceAction;
  sending: boolean;
}>();

const emit = defineEmits<{
  "send-message": [content: string];
  "trigger-action": [action: AgentCardAction | WorkspaceAction];
}>();

const draft = ref("");
const scrollArea = ref<HTMLElement | null>(null);

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
        <strong>请按照当前主操作推进任务。系统会根据任务状态校验每一步，不能跳过必要流程。</strong>
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
            当前主操作：{{ primaryAction?.label ?? "暂无可执行动作" }}
          </el-button>
        </el-tooltip>
      </div>
      <p v-if="!primaryAction || primaryAction.disabled" class="composer-state-hint">
        {{ primaryAction?.description ?? "当前没有可执行主操作。请先上传资料、刷新诊断，或等待后端完成上一阶段。" }}
      </p>
      <div class="composer-input">
        <span class="composer-input__label">本地备注，暂不参与生成</span>
        <el-input
          v-model="draft"
          :autosize="{ minRows: 2, maxRows: 3 }"
          type="textarea"
          resize="none"
          placeholder="可记录人工备注。当前版本不会把这里的内容提交给后端生成流程。"
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
