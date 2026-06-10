<script setup lang="ts">
import { computed, ref, watch } from "vue";
import type { UploadFile, UploadInstance, UploadProps, UploadRawFile } from "element-plus";
import { UploadFilled } from "@element-plus/icons-vue";

import type { SourceUploadType } from "@/api/sourceApi";

const props = defineProps<{
  modelValue: boolean;
  uploading: boolean;
  disabled: boolean;
  activeUploadType?: SourceUploadType;
}>();

const emit = defineEmits<{
  "update:modelValue": [value: boolean];
  submit: [payload: { uploadType: SourceUploadType; file: File }];
}>();

type UploadCategory = "reference" | "product";

const REFERENCE_ACCEPT = ".doc,.docx,.pdf,.md,.txt,.html";
const PRODUCT_ACCEPT = ".doc,.docx,.xls,.xlsx,.ppt,.pptx,.pdf,.md,.txt,.html,.png,.jpg,.jpeg,.webp";
const IMAGE_EXTENSIONS = new Set([".png", ".jpg", ".jpeg", ".webp"]);
const UPLOAD_TYPE_META: Record<
  UploadCategory,
  {
    title: string;
    description: string;
    alertType: "info" | "success" | "warning";
    fileHint: string;
    accept: string;
    boundary: string;
    tip: string;
  }
> = {
  reference: {
    title: "上传外部参考资料",
    description: "用于目录结构、章法、配图方式和语言风格参考，不作为产品事实来源。",
    alertType: "warning",
    fileHint: "支持 doc、docx、pdf、md、txt、html",
    accept: REFERENCE_ACCEPT,
    boundary: "仅参考目录、章法、配图方式和语言风格，不能作为产品事实来源。",
    tip: "请上传外部参考软著或相似文档。系统会隔离为风格参考，不进入产品事实依据。",
  },
  product: {
    title: "上传自有产品资料",
    description: "支持产品文档和产品截图。文档可作为产品事实依据；图片仅作为配图候选和展示。",
    alertType: "success",
    fileHint: "支持 doc、docx、xls、xlsx、ppt、pptx、pdf、md、txt、html、png、jpg、jpeg、webp",
    accept: PRODUCT_ACCEPT,
    boundary: "文档类资料可作为产品事实依据；图片仅作为配图候选和展示，不做 OCR，不作为产品事实证据。",
    tip: "请上传我方产品文档或产品截图。系统会根据文件格式在自有产品资料中区分产品文档和产品截图。",
  },
};

const uploadType = ref<UploadCategory>("reference");
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
    uploadType: resolveSubmitUploadType(uploadType.value, selectedFile.value),
    file: selectedFile.value,
  });
}

function handleFileChange(file: UploadFile) {
  selectedFile.value = file.raw ?? null;
}

function clearSelectedFile() {
  selectedFile.value = null;
  uploadRef.value?.clearFiles();
}

function fileMatchesAccept(file: File, accept: string): boolean {
  const fileName = file.name.toLowerCase();
  return accept
    .split(",")
    .map((extension) => extension.trim().toLowerCase())
    .some((extension) => fileName.endsWith(extension));
}

function fileExtension(file: File): string {
  const match = file.name.toLowerCase().match(/\.[^.]+$/);
  return match?.[0] ?? "";
}

function resolveSubmitUploadType(uploadCategory: UploadCategory, file: File): SourceUploadType {
  if (uploadCategory === "product" && IMAGE_EXTENSIONS.has(fileExtension(file))) {
    return "screenshots";
  }
  return uploadCategory;
}

function categoryFromActiveType(uploadType?: SourceUploadType): UploadCategory {
  return uploadType === "product" || uploadType === "screenshots" ? "product" : "reference";
}

function closeDialog() {
  if (!props.uploading) {
    emit("update:modelValue", false);
  }
}

watch(
  () => props.modelValue,
  (visible) => {
    if (visible) {
      uploadType.value = categoryFromActiveType(props.activeUploadType);
      clearSelectedFile();
      return;
    }

    clearSelectedFile();
  },
);

watch(
  () => props.activeUploadType,
  (activeUploadType) => {
    if (props.modelValue && activeUploadType) {
      uploadType.value = categoryFromActiveType(activeUploadType);
    }
  },
);

watch(uploadType, () => {
  if (selectedFile.value && !fileMatchesAccept(selectedFile.value, uploadTypeMeta.value.accept)) {
    clearSelectedFile();
  }
});
</script>

<template>
  <el-dialog
    :model-value="modelValue"
    :title="uploadTypeMeta.title"
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
        <span>{{ uploadTypeMeta.boundary }}</span>
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
        <div class="el-upload__text">拖拽文件到这里，或点击选择文件</div>
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
        上传
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
