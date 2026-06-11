<script setup lang="ts">
import { computed } from "vue";

import type { ParseStatus } from "@/types/workspace";

const props = defineProps<{
  status: ParseStatus;
  apiKeyConfigured: boolean;
  parsedTooltip: string;
  failedReason?: string | null;
}>();

type NormalizedStatus = "pending" | "parsing" | "parsed" | "failed" | "skipped";

const normalizedStatus = computed<NormalizedStatus>(() => {
  if (props.status === "parsed") {
    return "parsed";
  }
  if (props.status === "failed") {
    return "failed";
  }
  if (props.status === "skipped") {
    return "skipped";
  }
  if (props.status === "parsing" || props.status === "embedding") {
    return "parsing";
  }
  return "pending";
});

const label = computed(() => {
  if (normalizedStatus.value === "pending") {
    return props.apiKeyConfigured ? "待开始" : "待配置";
  }
  const labels: Record<Exclude<NormalizedStatus, "pending">, string> = {
    parsing: "解析中",
    parsed: "已解析",
    failed: "解析失败",
    skipped: "已跳过",
  };
  return labels[normalizedStatus.value];
});

const tagType = computed<"info" | "success" | "warning" | "danger">(() => {
  const types: Record<NormalizedStatus, "info" | "success" | "warning" | "danger"> = {
    pending: "info",
    parsing: "warning",
    parsed: "success",
    failed: "danger",
    skipped: "info",
  };
  return types[normalizedStatus.value];
});

const tooltip = computed(() => {
  if (normalizedStatus.value === "pending") {
    return props.apiKeyConfigured
      ? "资料已上传，模型密钥已可用。回复“开始”后系统将开始解析。"
      : "资料已上传。请先配置并测试模型密钥。";
  }
  if (normalizedStatus.value === "parsing") {
    return "正在解析资料并构建证据。";
  }
  if (normalizedStatus.value === "parsed") {
    return props.parsedTooltip;
  }
  if (normalizedStatus.value === "failed") {
    const reason = safeFailedReason(props.failedReason);
    return reason
      ? `资料解析失败：${reason}`
      : "资料解析失败，请检查文件格式、文件内容或后端服务配置。";
  }
  return "该资料已跳过解析。";
});

function safeFailedReason(reason?: string | null): string {
  const trimmed = reason?.trim() ?? "";
  if (!trimmed) {
    return "";
  }

  const lower = trimmed.toLowerCase();
  const looksInternal =
    lower.includes("traceback") ||
    lower.includes("python") ||
    lower.includes("exception") ||
    lower.includes("stack") ||
    trimmed.includes("/Users/") ||
    trimmed.includes("\\n  File ");

  if (looksInternal) {
    return "";
  }

  return trimmed.length > 120 ? `${trimmed.slice(0, 120)}...` : trimmed;
}
</script>

<template>
  <el-tooltip :content="tooltip" placement="top">
    <el-tag size="small" :type="tagType" effect="plain" class="source-status-badge">
      {{ label }}
    </el-tag>
  </el-tooltip>
</template>

<style scoped>
.source-status-badge {
  max-width: 76px;
  justify-content: center;
}
</style>
