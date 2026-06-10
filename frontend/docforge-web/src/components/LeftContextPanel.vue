<script setup lang="ts">
import { computed } from "vue";
import { Collection, Document, Plus, Tickets } from "@element-plus/icons-vue";

import SourceDropzoneCard from "@/components/SourceDropzoneCard.vue";
import SourceListItem from "@/components/SourceListItem.vue";
import type { SourceUploadType } from "@/api/sourceApi";
import type { ExportArtifact, FileType, SourceItem } from "@/types/workspace";

const props = defineProps<{
  sources: SourceItem[];
  exportArtifacts: ExportArtifact[];
  downloadingArtifactId: string | null;
  apiKeyConfigured: boolean;
}>();

defineEmits<{
  "select-source": [source: SourceItem];
  "download-artifact": [artifact: ExportArtifact];
  "open-upload": [uploadType: SourceUploadType];
}>();

const imageFileTypes = new Set<FileType>(["png", "jpg", "jpeg", "webp"]);

const externalReferences = computed(() =>
  props.sources.filter((source) => source.sourceType === "reference_soft_copyright_doc"),
);

const productDocuments = computed(() =>
  props.sources.filter(
    (source) =>
      source.allowedUsage === "factual_evidence" &&
      source.sourceType !== "screenshot" &&
      !imageFileTypes.has(source.fileType),
  ),
);

const productImages = computed(() =>
  props.sources.filter(
    (source) =>
      source.sourceType === "screenshot" ||
      source.allowedUsage === "display_material_only" ||
      imageFileTypes.has(source.fileType),
  ),
);

const hasOwnProductSources = computed(
  () => productDocuments.value.length > 0 || productImages.value.length > 0,
);
</script>

<template>
  <aside class="left-panel" aria-label="资料与导出历史">
    <section class="left-panel__section">
      <div class="section-title section-title--with-action">
        <span>
          <el-icon><Collection /></el-icon>
          外部参考资料
        </span>
        <el-button
          v-if="externalReferences.length > 0"
          size="small"
          link
          :icon="Plus"
          @click="$emit('open-upload', 'reference')"
        >
          上传
        </el-button>
      </div>

      <SourceDropzoneCard
        v-if="externalReferences.length === 0"
        title="上传外部参考资料"
        description="用于参考软著目录、章节写法、配图方式和语言风格，不作为产品事实来源。"
        compact
        @click="$emit('open-upload', 'reference')"
      />
      <div v-else class="source-list">
        <SourceListItem
          v-for="source in externalReferences"
          :key="source.sourceId"
          :source="source"
          variant="reference"
          :api-key-configured="apiKeyConfigured"
          @select="$emit('select-source', $event)"
        />
      </div>
    </section>

    <section class="left-panel__section">
      <div class="section-title section-title--with-action">
        <span>
          <el-icon><Tickets /></el-icon>
          自有产品资料
        </span>
        <el-button
          v-if="hasOwnProductSources"
          size="small"
          link
          :icon="Plus"
          @click="$emit('open-upload', 'product')"
        >
          上传
        </el-button>
      </div>

      <SourceDropzoneCard
        v-if="!hasOwnProductSources"
        title="上传自有产品资料"
        description="支持产品文档和产品截图。文档可作为产品事实依据；截图仅用于配图候选和展示，不作为事实证据。"
        compact
        @click="$emit('open-upload', 'product')"
      />

      <div v-else class="source-groups">
        <div class="source-group">
          <div class="source-group__head">
            <strong>产品文档</strong>
            <span>用于提取产品功能、技术架构和业务流程，可作为生成软著正文的事实依据。</span>
          </div>
          <div v-if="productDocuments.length > 0" class="source-list">
            <SourceListItem
              v-for="source in productDocuments"
              :key="source.sourceId"
              :source="source"
              variant="product-document"
              :api-key-configured="apiKeyConfigured"
              @select="$emit('select-source', $event)"
            />
          </div>
          <p v-else class="source-group__empty">尚未上传产品文档。</p>
        </div>

        <div class="source-group">
          <div class="source-group__head">
            <strong>产品截图</strong>
            <span>仅用于配图候选和展示，不做 OCR，不作为产品事实证据。</span>
          </div>
          <div v-if="productImages.length > 0" class="source-list">
            <SourceListItem
              v-for="source in productImages"
              :key="source.sourceId"
              :source="source"
              variant="product-image"
              :api-key-configured="apiKeyConfigured"
              @select="$emit('select-source', $event)"
            />
          </div>
          <p v-else class="source-group__empty">尚未上传产品截图。</p>
        </div>
      </div>
    </section>

    <section class="left-panel__section">
      <div class="section-title">
        <span>
          <el-icon><Document /></el-icon>
          生成产物 / 导出历史
        </span>
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
  margin-top: 16px;
}

.section-title {
  display: flex;
  align-items: center;
  margin-bottom: 8px;
  color: var(--df-text-secondary);
  font-size: 13px;
  font-weight: 700;
}

.section-title span {
  display: inline-flex;
  align-items: center;
  min-width: 0;
  gap: 7px;
}

.section-title--with-action {
  justify-content: space-between;
  gap: 10px;
}

.source-list {
  display: grid;
  gap: 6px;
}

.source-groups {
  display: grid;
  gap: 10px;
}

.source-group {
  display: grid;
  gap: 7px;
}

.source-group__head {
  display: grid;
  gap: 3px;
  padding: 0 2px;
}

.source-group__head strong {
  color: var(--df-text);
  font-size: 12px;
  line-height: 1.35;
}

.source-group__head span,
.source-group__empty {
  color: var(--df-text-secondary);
  font-size: 11px;
  line-height: 1.45;
}

.source-group__empty {
  margin: 0;
  padding: 8px 9px;
  border: 1px dashed var(--df-border);
  border-radius: var(--df-radius-md);
  background: rgba(255, 255, 255, 0.58);
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
