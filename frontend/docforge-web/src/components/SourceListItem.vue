<script setup lang="ts">
import { computed } from "vue";
import { Camera, Document } from "@element-plus/icons-vue";

import SourceStatusBadge from "@/components/SourceStatusBadge.vue";
import type { SourceItem } from "@/types/workspace";

const props = defineProps<{
  source: SourceItem;
  variant: "reference" | "product-document" | "product-image";
  apiKeyConfigured: boolean;
}>();

defineEmits<{
  select: [source: SourceItem];
}>();

const isParsing = computed(
  () => props.source.parseStatus === "parsing" || props.source.parseStatus === "embedding",
);

const progress = computed(() => {
  const rawProgress = props.source.metadata?.progress;
  if (typeof rawProgress !== "number" || Number.isNaN(rawProgress)) {
    return null;
  }
  return Math.min(100, Math.max(0, rawProgress));
});

const progressStyle = computed(() => ({
  "--source-progress": `${progress.value ?? 42}%`,
}));

const parsedTooltip = computed(() => {
  if (props.variant === "reference") {
    return "资料已完成解析，但仅用于参考目录、章法、配图方式和语言风格，不能作为产品事实来源。";
  }
  if (props.variant === "product-image") {
    return "图片已登记，仅用于配图候选和展示，不做 OCR，不作为产品事实证据。";
  }
  return "资料已完成解析，可参与后续生成流程。";
});

const boundary = computed(() => {
  if (props.variant === "reference") {
    return "仅参考目录、章法、配图方式和语言风格；不能作为产品事实来源";
  }
  if (props.variant === "product-image") {
    return "仅用于配图候选和展示；不做 OCR，不作为事实证据";
  }
  return "用于提取产品功能、技术架构和业务流程；可作为事实依据";
});
</script>

<template>
  <button
    class="source-list-item"
    :class="{
      'source-list-item--reference': variant === 'reference',
      'source-list-item--image': variant === 'product-image',
      'source-list-item--parsing': isParsing,
      'source-list-item--indeterminate': isParsing && progress === null,
    }"
    type="button"
    @click="$emit('select', source)"
  >
    <span class="source-list-item__icon">
      <el-icon v-if="variant === 'product-image'"><Camera /></el-icon>
      <el-icon v-else><Document /></el-icon>
    </span>
    <span class="source-list-item__main">
      <span class="source-list-item__name-track" :style="progressStyle">
        <strong class="source-list-item__name" :title="source.fileName">{{ source.fileName }}</strong>
      </span>
      <span class="source-list-item__boundary">{{ boundary }}</span>
    </span>
    <SourceStatusBadge
      :status="source.parseStatus"
      :api-key-configured="apiKeyConfigured"
      :parsed-tooltip="parsedTooltip"
      :failed-reason="source.parseError"
    />
  </button>
</template>

<style scoped>
.source-list-item {
  display: grid;
  grid-template-columns: 20px minmax(0, 1fr) auto;
  align-items: center;
  width: 100%;
  gap: 8px;
  padding: 8px 9px;
  text-align: left;
  border: 1px solid var(--df-border);
  border-radius: var(--df-radius-md);
  background: var(--df-surface);
  cursor: pointer;
  transition:
    border-color 0.16s ease,
    box-shadow 0.16s ease;
}

.source-list-item:hover {
  border-color: var(--df-primary);
  box-shadow: var(--df-shadow-sm);
}

.source-list-item--reference {
  border-color: #f5d690;
  background: #fffaf0;
}

.source-list-item--image {
  border-color: var(--df-info-border);
  background: #f8fbff;
}

.source-list-item__icon {
  display: grid;
  place-items: center;
  color: var(--df-text-secondary);
  font-size: 15px;
}

.source-list-item__main {
  display: grid;
  min-width: 0;
  gap: 4px;
}

.source-list-item__name-track {
  position: relative;
  min-width: 0;
  overflow: hidden;
  border-radius: 5px;
}

.source-list-item--parsing .source-list-item__name-track::before {
  position: absolute;
  inset: 0 auto 0 0;
  width: var(--source-progress);
  border-radius: inherit;
  background: #fef3c7;
  content: "";
}

.source-list-item--indeterminate .source-list-item__name-track::before {
  width: 44%;
  animation: source-name-progress 1.2s infinite ease-in-out;
}

.source-list-item__name {
  position: relative;
  display: block;
  min-width: 0;
  overflow: hidden;
  color: var(--df-text);
  font-size: 12px;
  line-height: 1.35;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.source-list-item__boundary {
  display: block;
  overflow: hidden;
  color: var(--df-text-secondary);
  font-size: 11px;
  line-height: 1.35;
  text-overflow: ellipsis;
  white-space: nowrap;
}

@keyframes source-name-progress {
  0% {
    left: -44%;
  }

  100% {
    left: 100%;
  }
}
</style>
