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
  const labels: Record<NormalizedStatus, string> = {
    pending: "待解析",
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
      ? "资料已上传，等待后端解析。"
      : "未配置模型 API 密钥，资料待解析。当前版本真实解析仍以后端服务配置为准。";
  }
  if (normalizedStatus.value === "parsing") {
    return "正在解析资料并写入知识库，当前版本暂不显示具体百分比。";
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
