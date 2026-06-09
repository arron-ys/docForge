<script setup lang="ts">
import { computed } from "vue";
import {
  Camera,
  Collection,
  Document,
  FolderOpened,
  Tickets,
} from "@element-plus/icons-vue";

import type { ExportArtifact, RunSummary, SourceItem } from "@/types/workspace";

const props = defineProps<{
  run: RunSummary;
  sources: SourceItem[];
  exportArtifacts: ExportArtifact[];
  downloadingArtifactId: string | null;
}>();

defineEmits<{
  "select-source": [source: SourceItem];
  "download-artifact": [artifact: ExportArtifact];
}>();

const externalReferences = computed(() =>
  props.sources.filter((source) => source.sourceType === "reference_soft_copyright_doc"),
);
const ownProductSources = computed(() =>
  props.sources.filter((source) => source.allowedUsage === "factual_evidence"),
);
const screenshots = computed(() => props.sources.filter((source) => source.sourceType === "screenshot"));
</script>

<template>
  <aside class="left-panel" aria-label="Agent 可用上下文仓库">
    <section class="left-panel__section">
      <div class="section-title">
        <el-icon><FolderOpened /></el-icon>
        当前运行任务
      </div>
      <el-card shadow="never" class="task-card">
        <strong>{{ run.taskName }}</strong>
        <span>{{ run.stageLabel }}</span>
      </el-card>
    </section>

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
        <el-tag size="small" :type="source.usagePolicy.badgeType">{{ source.statusLabel }}</el-tag>
        <span class="source-card__policy">{{ source.usagePolicy.allowedUse }}</span>
        <span class="source-card__risk">{{ source.usagePolicy.riskBoundary }}</span>
      </button>
      <p v-if="externalReferences.length === 0" class="empty-note">
        尚未上传外部参考资料。上传后仅用于目录、章法、配图方式和语言风格。
      </p>
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
        <el-tag size="small" :type="source.usagePolicy.badgeType">{{ source.statusLabel }}</el-tag>
        <span class="source-card__policy">{{ source.usagePolicy.allowedUse }}</span>
        <span class="source-card__risk">{{ source.usagePolicy.riskBoundary }}</span>
      </button>
      <p v-if="ownProductSources.length === 0" class="empty-note">
        尚未上传自有产品资料。可作为产品事实来源的是 product_evidence / factual_evidence。
      </p>
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
        <el-tag size="small" :type="source.usagePolicy.badgeType">{{ source.statusLabel }}</el-tag>
        <span class="source-card__policy">{{ source.usagePolicy.allowedUse }}</span>
        <span class="source-card__risk">{{ source.usagePolicy.riskBoundary }}</span>
      </button>
      <p v-if="screenshots.length === 0" class="empty-note">
        尚未上传产品截图。截图仅作为配图候选和展示材料登记，MVP 不做 OCR，不作为强产品事实证据。
      </p>
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

.task-card {
  border-radius: var(--df-radius-md);
}

.task-card :deep(.el-card__body) {
  display: grid;
  gap: 6px;
  padding: 12px;
}

.task-card strong {
  color: var(--df-text);
  font-size: 13px;
  line-height: 1.45;
}

.task-card span {
  color: var(--df-text-secondary);
  font-size: 12px;
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
.source-card__risk {
  color: var(--df-text-secondary);
  font-size: 12px;
  line-height: 1.45;
}

.source-card__risk {
  color: var(--df-warning-text);
}

.empty-note {
  margin: 0;
  padding: 10px 12px;
  border: 1px dashed var(--df-border);
  border-radius: var(--df-radius-md);
  background: rgba(255, 255, 255, 0.62);
  color: var(--df-text-secondary);
  font-size: 12px;
  line-height: 1.55;
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
