<script setup lang="ts">
import { computed, ref, watch } from "vue";
import type { UploadFile, UploadInstance, UploadProps, UploadRawFile } from "element-plus";
import { UploadFilled } from "@element-plus/icons-vue";

import type { SourceUploadType } from "@/api/sourceApi";

const props = defineProps<{
  modelValue: boolean;
  uploading: boolean;
  disabled: boolean;
}>();

const emit = defineEmits<{
  "update:modelValue": [value: boolean];
  submit: [payload: { uploadType: SourceUploadType; file: File }];
}>();

const DOCUMENT_ACCEPT = ".docx,.pdf,.md,.txt,.html";
const SCREENSHOT_ACCEPT = ".png,.jpg,.jpeg,.webp";
const UPLOAD_TYPE_META: Record<
  SourceUploadType,
  {
    title: string;
    description: string;
    alertType: "info" | "success" | "warning";
    fileHint: string;
    accept: string;
    factBoundary: string;
    tip: string;
  }
> = {
  reference: {
    title: "外部参考资料只学习写法",
    description: "用于目录结构、章法、配图方式和语言风格参考，不作为产品事实来源。",
    alertType: "warning",
    fileHint: "docx、pdf、md、txt、html",
    accept: DOCUMENT_ACCEPT,
    factBoundary: "写入 reference_style / style_only。",
    tip: "请上传外部参考软著或相似文档。系统会隔离为风格参考，不进入产品事实链。",
  },
  product: {
    title: "自有产品资料可作为事实来源",
    description: "用于产品能力描述、事实归纳和后续 evidence-grounded 校验。",
    alertType: "success",
    fileHint: "docx、pdf、md、txt、html",
    accept: DOCUMENT_ACCEPT,
    factBoundary: "写入 product_evidence / factual_evidence。",
    tip: "请上传我方产品介绍、PRD、设计说明等资料。后端状态机会决定何时解析和推进。",
  },
  screenshots: {
    title: "产品截图只登记为展示材料",
    description:
      "当前阶段仅作为配图候选和展示材料登记，MVP 不做 OCR，不作为强产品事实证据，也不用于推断当前版本已实现功能。",
    alertType: "info",
    fileHint: "png、jpg、jpeg、webp",
    accept: SCREENSHOT_ACCEPT,
    factBoundary: "写入 product_evidence / display_material_only。",
    tip: "截图仅登记为 display_material_only：仅作为配图候选和展示材料登记，MVP 不做 OCR，不作为强产品事实证据。",
  },
};

const uploadType = ref<SourceUploadType>("reference");
const selectedFile = ref<File | null>(null);
const uploadRef = ref<UploadInstance>();

const uploadTypeMeta = computed(() => UPLOAD_TYPE_META[uploadType.value]);

const beforeUpload: UploadProps["beforeUpload"] = (rawFile: UploadRawFile) => {
  selectedFile.value = rawFile;
  return false;
};

function submitUpload() {
  if (!selectedFile.value || props.uploading || props.disabled) {
    return;
  }

  emit("submit", {
    uploadType: uploadType.value,
    file: selectedFile.value,
  });
}

function handleFileChange(file: UploadFile) {
  selectedFile.value = file.raw ?? null;
}

function closeDialog() {
  if (!props.uploading) {
    emit("update:modelValue", false);
  }
}

watch(
  () => props.modelValue,
  (visible) => {
    if (!visible) {
      selectedFile.value = null;
      uploadRef.value?.clearFiles();
      uploadType.value = "reference";
    }
  },
);
</script>

<template>
  <el-dialog
    :model-value="modelValue"
    title="上传资料"
    width="520px"
    :close-on-click-modal="!uploading"
    :close-on-press-escape="!uploading"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <div class="upload-dialog">
      <el-alert
        v-if="disabled"
        title="请先选择任务"
        description="URL 中需要带 run_id，例如 /?run_id=20260609_143000_ab12。"
        type="warning"
        show-icon
        :closable="false"
      />

      <el-radio-group v-model="uploadType" class="upload-dialog__types" :disabled="disabled || uploading">
        <el-radio-button value="reference">外部参考资料</el-radio-button>
        <el-radio-button value="product">自有产品资料</el-radio-button>
        <el-radio-button value="screenshots">产品截图</el-radio-button>
      </el-radio-group>

      <el-alert
        :title="uploadTypeMeta.title"
        :description="uploadTypeMeta.description"
        :type="uploadTypeMeta.alertType"
        show-icon
        :closable="false"
      />

      <div class="upload-dialog__policy">
        <span>允许文件：{{ uploadTypeMeta.fileHint }}</span>
        <span>{{ uploadTypeMeta.factBoundary }}</span>
      </div>

      <el-upload
        ref="uploadRef"
        drag
        :accept="uploadTypeMeta.accept"
        :auto-upload="false"
        :limit="1"
        :disabled="disabled || uploading"
        :before-upload="beforeUpload"
        :on-change="handleFileChange"
      >
        <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
        <div class="el-upload__text">拖拽文件到这里，或 <em>点击选择</em></div>
        <template #tip>
          <div class="el-upload__tip">
            {{ uploadTypeMeta.tip }}
          </div>
        </template>
      </el-upload>
    </div>

    <template #footer>
      <el-button :disabled="uploading" @click="closeDialog">取消</el-button>
      <el-button
        type="primary"
        :loading="uploading"
        :disabled="disabled || !selectedFile"
        @click="submitUpload"
      >
        上传并登记
      </el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.upload-dialog {
  display: grid;
  gap: 16px;
}

.upload-dialog__types {
  width: 100%;
}

.upload-dialog__types :deep(.el-radio-button) {
  flex: 1;
}

.upload-dialog__types :deep(.el-radio-button__inner) {
  width: 100%;
}

.upload-dialog__policy {
  display: grid;
  gap: 6px;
  padding: 10px 12px;
  border: 1px solid var(--df-border);
  border-radius: var(--df-radius-md);
  background: var(--df-muted);
  color: var(--df-text-secondary);
  font-size: 12px;
  line-height: 1.5;
}
</style>
