<script setup lang="ts">
import { computed } from "vue";
import { Camera, Collection, Document, Tickets } from "@element-plus/icons-vue";

import SourceDropzoneCard from "@/components/SourceDropzoneCard.vue";
import type { SourceUploadType } from "@/api/sourceApi";
import type { ExportArtifact, ParseStatus, SourceItem, SourceUsagePolicy } from "@/types/workspace";

const props = defineProps<{
  sources: SourceItem[];
  exportArtifacts: ExportArtifact[];
  downloadingArtifactId: string | null;
}>();

defineEmits<{
  "select-source": [source: SourceItem];
  "download-artifact": [artifact: ExportArtifact];
  "open-upload": [uploadType: SourceUploadType];
}>();

const externalReferences = computed(() =>
  props.sources.filter((source) => source.sourceType === "reference_soft_copyright_doc"),
);
const ownProductSources = computed(() =>
  props.sources.filter((source) => source.allowedUsage === "factual_evidence"),
);
const screenshots = computed(() => props.sources.filter((source) => source.sourceType === "screenshot"));

type SourceStatusTone = "pending" | "parsed" | "failed" | "skipped" | "saved";

const SOURCE_STATUS_META: Record<
  ParseStatus,
  {
    label: string;
    tagType: "info" | "success" | "warning" | "danger";
    tone: SourceStatusTone;
  }
> = {
  pending: {
    label: "已上传，等待点击“开始解析资料”",
    tagType: "info",
    tone: "pending",
  },
  parsed: {
    label: "解析完成",
    tagType: "success",
    tone: "parsed",
  },
  failed: {
    label: "解析失败，点击查看原因",
    tagType: "danger",
    tone: "failed",
  },
  skipped: {
    label: "已跳过解析",
    tagType: "info",
    tone: "skipped",
  },
  saved: {
    label: "已上传，等待解析",
    tagType: "info",
    tone: "saved",
  },
};

function sourceStatusMeta(source: SourceItem) {
  return SOURCE_STATUS_META[source.parseStatus];
}

function sourceUsageCopy(source: SourceItem): SourceUsagePolicy {
  if (source.allowedUsage === "style_only") {
    return {
      label: "外部参考资料",
      allowedUse: "仅参考目录、章法、配图方式和语言风格",
      riskBoundary: "不能作为产品事实来源",
      badgeType: "warning",
    };
  }

  if (source.allowedUsage === "factual_evidence") {
    return {
      label: "自有产品资料",
      allowedUse: "可作为产品事实依据",
      riskBoundary: "系统会基于证据提取能力、状态和置信度使用",
      badgeType: "success",
    };
  }

  if (source.allowedUsage === "display_material_only") {
    return {
      label: "产品截图",
      allowedUse: "仅用于配图和展示",
      riskBoundary: "不做 OCR，不作为产品事实证据",
      badgeType: "info",
    };
  }

  return source.usagePolicy;
}
</script>

<template>
  <aside class="left-panel" aria-label="资料与导出历史">
    <section class="left-panel__section">
      <div class="section-title">
        <el-icon><Collection /></el-icon>
        外部参考资料
      </div>
      <button
        v-for="source in externalReferences"
        :key="source.sourceId"
        class="source-card"
        type="button"
        @click="$emit('select-source', source)"
      >
        <span class="source-card__head">
          <el-icon><Document /></el-icon>
          <strong>{{ source.fileName }}</strong>
        </span>
        <el-tag size="small" :type="sourceStatusMeta(source).tagType">
          {{ sourceStatusMeta(source).label }}
        </el-tag>
        <span
          v-if="source.parseStatus === 'pending' || source.parseStatus === 'failed'"
          class="source-card__status"
          :class="`source-card__status--${sourceStatusMeta(source).tone}`"
          :title="source.parseStatus === 'failed' ? source.parseError ?? undefined : undefined"
        >
          {{ sourceStatusMeta(source).label }}
        </span>
        <span class="source-card__policy">{{ sourceUsageCopy(source).allowedUse }}</span>
        <span class="source-card__risk">{{ sourceUsageCopy(source).riskBoundary }}</span>
      </button>
      <SourceDropzoneCard
        v-if="externalReferences.length === 0"
        title="上传外部参考资料"
        description="用于参考软著目录、章节写法、配图方式和语言风格，不作为产品事实来源。"
        @click="$emit('open-upload', 'reference')"
      />
    </section>

    <section class="left-panel__section">
      <div class="section-title">
        <el-icon><Tickets /></el-icon>
        自有产品资料
      </div>
      <button
        v-for="source in ownProductSources"
        :key="source.sourceId"
        class="source-card source-card--success"
        type="button"
        @click="$emit('select-source', source)"
      >
        <span class="source-card__head">
          <el-icon><Document /></el-icon>
          <strong>{{ source.fileName }}</strong>
        </span>
        <el-tag size="small" :type="sourceStatusMeta(source).tagType">
          {{ sourceStatusMeta(source).label }}
        </el-tag>
        <span
          v-if="source.parseStatus === 'pending' || source.parseStatus === 'failed'"
          class="source-card__status"
          :class="`source-card__status--${sourceStatusMeta(source).tone}`"
          :title="source.parseStatus === 'failed' ? source.parseError ?? undefined : undefined"
        >
          {{ sourceStatusMeta(source).label }}
        </span>
        <span class="source-card__policy">{{ sourceUsageCopy(source).allowedUse }}</span>
        <span class="source-card__risk">{{ sourceUsageCopy(source).riskBoundary }}</span>
      </button>
      <SourceDropzoneCard
        v-if="ownProductSources.length === 0"
        title="上传自有产品资料"
        description="用于提取产品功能、技术架构和业务流程，是生成软著正文的事实依据。"
        @click="$emit('open-upload', 'product')"
      />
    </section>

    <section class="left-panel__section">
      <div class="section-title">
        <el-icon><Camera /></el-icon>
        产品截图
      </div>
      <button
        v-for="source in screenshots"
        :key="source.sourceId"
        class="source-card source-card--info"
        type="button"
        @click="$emit('select-source', source)"
      >
        <span class="source-card__head">
          <el-icon><Camera /></el-icon>
          <strong>{{ source.fileName }}</strong>
        </span>
        <el-tag size="small" :type="sourceStatusMeta(source).tagType">
          {{ sourceStatusMeta(source).label }}
        </el-tag>
        <span
          v-if="source.parseStatus === 'pending' || source.parseStatus === 'failed'"
          class="source-card__status"
          :class="`source-card__status--${sourceStatusMeta(source).tone}`"
          :title="source.parseStatus === 'failed' ? source.parseError ?? undefined : undefined"
        >
          {{ sourceStatusMeta(source).label }}
        </span>
        <span class="source-card__policy">{{ sourceUsageCopy(source).allowedUse }}</span>
        <span class="source-card__risk">{{ sourceUsageCopy(source).riskBoundary }}</span>
      </button>
      <SourceDropzoneCard
        v-if="screenshots.length === 0"
        title="上传产品截图"
        description="仅作为配图候选和展示材料，不做 OCR，不作为产品事实证据。"
        @click="$emit('open-upload', 'screenshots')"
      />
    </section>

    <section class="left-panel__section">
      <div class="section-title">
        <el-icon><Document /></el-icon>
        生成产物 / 导出历史
      </div>
      <div class="artifact-list">
        <div v-for="artifact in exportArtifacts" :key="artifact.artifactId" class="artifact-item">
          <div class="artifact-item__meta">
            <span>{{ artifact.name }}</span>
            <el-tag size="small" type="info" effect="plain">{{ artifact.statusLabel }}</el-tag>
          </div>
          <el-button
            size="small"
            plain
            :loading="downloadingArtifactId === artifact.artifactId"
            :disabled="!artifact.downloadable"
            @click="$emit('download-artifact', artifact)"
          >
            下载
          </el-button>
          <p v-if="!artifact.downloadable" class="artifact-item__hint">
            文档尚未生成，完成正文生成和风险检查后才可下载。
          </p>
        </div>
      </div>
    </section>
  </aside>
</template>

<style scoped>
.left-panel {
  height: 100%;
  overflow-y: auto;
  background: var(--df-panel);
  padding: 16px 14px;
}

.left-panel__section + .left-panel__section {
  margin-top: 18px;
}

.section-title {
  display: flex;
  align-items: center;
  gap: 7px;
  margin-bottom: 8px;
  color: var(--df-text-secondary);
  font-size: 13px;
  font-weight: 700;
}

.source-card {
  display: grid;
  width: 100%;
  gap: 8px;
  margin-bottom: 10px;
  padding: 12px;
  text-align: left;
  border: 1px solid var(--df-warning-border);
  border-radius: var(--df-radius-md);
  background: #fffaf0;
  cursor: pointer;
  transition:
    border-color 0.16s ease,
    box-shadow 0.16s ease;
}

.source-card:hover {
  border-color: var(--df-primary);
  box-shadow: var(--df-shadow-sm);
}

.source-card--success {
  border-color: var(--df-success-border);
  background: #f6fffb;
}

.source-card--info {
  border-color: var(--df-info-border);
  background: #f5f8ff;
}

.source-card__head {
  display: flex;
  align-items: flex-start;
  gap: 7px;
  color: var(--df-text);
  font-size: 13px;
  line-height: 1.35;
}

.source-card__policy,
.source-card__risk,
.source-card__status {
  color: var(--df-text-secondary);
  font-size: 12px;
  line-height: 1.45;
}

.source-card__status {
  display: grid;
  gap: 6px;
}

.source-card__status--parsed {
  color: #047857;
}

.source-card__status--failed {
  color: var(--df-danger);
}

.source-card__status--pending {
  color: #b45309;
}

.source-card__risk {
  color: var(--df-warning-text);
}

.artifact-list {
  display: grid;
  gap: 8px;
}

.artifact-item {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 10px;
  padding: 10px 12px;
  border: 1px solid var(--df-border);
  border-radius: var(--df-radius-md);
  background: var(--df-surface);
  color: var(--df-text);
  font-size: 13px;
}

.artifact-item__meta {
  display: grid;
  min-width: 0;
  gap: 6px;
}

.artifact-item__hint {
  grid-column: 1 / -1;
  margin: 0;
  color: var(--df-text-secondary);
  font-size: 12px;
  line-height: 1.5;
}

</style>
