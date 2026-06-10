<script setup lang="ts">
import { computed } from "vue";
import { Key, Monitor, Odometer, Pointer, WarningFilled } from "@element-plus/icons-vue";

import type { RunSummary, WorkspaceAction } from "@/types/workspace";

const props = defineProps<{
  run: RunSummary;
  primaryAction?: WorkspaceAction;
  apiKeyConfigured: boolean;
}>();

defineEmits<{
  "open-api-key-config": [];
}>();

const taskLabel = computed(() => {
  const normalizedTaskName = props.run.taskName.replace(/^当前运行任务[:：]\s*/, "").trim();
  return `当前任务：${normalizedTaskName || props.run.runId}`;
});

const apiKeyTooltip = computed(() =>
  props.apiKeyConfigured
    ? "已保存运行时模型配置。后端模型调用将优先使用该配置。"
    : "配置 LLM 和 Embedding 模型密钥。未配置时后端将尝试使用 .env 默认配置。",
);
</script>

<template>
  <header class="top-bar">
    <div class="top-bar__brand">
      <div class="top-bar__logo">墨</div>
      <div>
        <h1>墨衡 DocForge</h1>
        <p>{{ run.projectName }}</p>
        <span class="top-bar__task">{{ taskLabel }}</span>
      </div>
    </div>

    <div class="top-bar__meta">
      <el-tag effect="plain" type="success" round>
        <el-icon><Pointer /></el-icon>
        {{ primaryAction ? `下一步：${primaryAction.label}` : "暂无可执行主操作" }}
      </el-tag>
      <el-tag effect="plain" type="info" round>
        <el-icon><Monitor /></el-icon>
        {{ run.stageLabel }}
      </el-tag>
      <el-tag effect="plain" :type="run.healthTone" round>
        <el-icon><Odometer /></el-icon>
        {{ run.healthLabel }}
      </el-tag>
      <el-tooltip :content="apiKeyTooltip" placement="bottom">
        <el-button
          :class="{ 'top-bar__key-button--warning': !apiKeyConfigured }"
          :icon="apiKeyConfigured ? Key : WarningFilled"
          :type="apiKeyConfigured ? 'primary' : 'warning'"
          @click="$emit('open-api-key-config')"
        >
          配置密钥
        </el-button>
      </el-tooltip>
    </div>
  </header>
</template>

<style scoped>
.top-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 56px;
  padding: 0 20px;
  border-bottom: 1px solid var(--df-border);
  background: var(--df-surface);
}

.top-bar__brand {
  display: flex;
  align-items: center;
  min-width: 0;
  max-width: 520px;
  gap: 12px;
}

.top-bar__logo {
  display: grid;
  width: 34px;
  height: 34px;
  place-items: center;
  border-radius: 10px;
  background: var(--df-primary);
  color: #fff;
  font-weight: 700;
}

.top-bar h1 {
  margin: 0;
  color: var(--df-text);
  font-size: 17px;
  font-weight: 700;
  line-height: 1.2;
}

.top-bar p {
  margin: 2px 0 0;
  color: var(--df-text-secondary);
  font-size: 12px;
}

.top-bar__task {
  display: block;
  max-width: 360px;
  overflow: hidden;
  color: var(--df-text-secondary);
  font-size: 11px;
  line-height: 1.3;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.top-bar__meta {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  min-width: 0;
  flex-wrap: wrap;
  gap: 10px;
}

.top-bar__meta :deep(.el-tag__content) {
  display: inline-flex;
  align-items: center;
  gap: 5px;
}

.top-bar__key-button--warning {
  border-color: #f59e0b;
  background: #f59e0b;
  color: #fff;
  font-weight: 700;
}

.top-bar__key-button--warning:hover,
.top-bar__key-button--warning:focus {
  border-color: #d97706;
  background: #d97706;
  color: #fff;
}
</style>
