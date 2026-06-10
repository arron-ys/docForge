<script setup lang="ts">
import { reactive, watch } from "vue";
import { ElMessage } from "element-plus";

import type { ApiKeyConfigState, EmbeddingModelOption, LlmModelOption } from "@/types/workspace";

const props = defineProps<{
  modelValue: boolean;
  config: ApiKeyConfigState;
}>();

const emit = defineEmits<{
  "update:modelValue": [value: boolean];
  save: [config: ApiKeyConfigState];
}>();

const form = reactive<ApiKeyConfigState>({
  llmModel: "qwen",
  llmApiKey: "",
  embeddingModel: "jina",
  embeddingApiKey: "",
});

const llmModelOptions: Array<{ label: string; value: LlmModelOption }> = [
  { label: "Qwen", value: "qwen" },
  { label: "DeepSeek", value: "deepseek" },
];

const embeddingModelOptions: Array<{ label: string; value: EmbeddingModelOption }> = [
  { label: "Jina", value: "jina" },
];

function syncForm() {
  form.llmModel = props.config.llmModel;
  form.llmApiKey = props.config.llmApiKey;
  form.embeddingModel = props.config.embeddingModel;
  form.embeddingApiKey = props.config.embeddingApiKey;
}

function closeDialog() {
  emit("update:modelValue", false);
}

function saveConfig() {
  emit("save", { ...form });
  ElMessage.success("模型密钥配置已在当前页面记录。当前版本真实调用仍以后端服务配置为准。");
  closeDialog();
}

watch(
  () => props.modelValue,
  (visible) => {
    if (visible) {
      syncForm();
    }
  },
);
</script>

<template>
  <el-dialog
    :model-value="modelValue"
    title="配置模型密钥"
    width="620px"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <div class="api-key-dialog">
      <section class="api-key-dialog__section">
        <h3>LLM 模型</h3>
        <label>
          <span>选择 LLM 模型</span>
          <el-select v-model="form.llmModel" class="api-key-dialog__control">
            <el-option
              v-for="option in llmModelOptions"
              :key="option.value"
              :label="option.label"
              :value="option.value"
            />
          </el-select>
        </label>
        <label>
          <span>LLM API Key</span>
          <el-input
            v-model="form.llmApiKey"
            autocomplete="off"
            class="api-key-dialog__control"
            placeholder="请输入所选 LLM 模型的 API Key"
            type="password"
          />
        </label>
        <p>
          用于后续调用大模型完成资料理解、软著写作和风险检查。当前版本仅保存本页面输入状态，真实调用仍以后端服务配置为准。
        </p>
      </section>

      <section class="api-key-dialog__section">
        <h3>Embedding 模型</h3>
        <label>
          <span>选择 Embedding 模型</span>
          <el-select v-model="form.embeddingModel" class="api-key-dialog__control">
            <el-option
              v-for="option in embeddingModelOptions"
              :key="option.value"
              :label="option.label"
              :value="option.value"
            />
          </el-select>
        </label>
        <label>
          <span>Embedding API Key</span>
          <el-input
            v-model="form.embeddingApiKey"
            autocomplete="off"
            class="api-key-dialog__control"
            placeholder="请输入 Jina Embedding API Key"
            type="password"
          />
        </label>
        <p>
          用于后续将上传资料向量化并写入知识库。当前版本仅保存本页面输入状态，真实调用仍以后端服务配置为准。
        </p>
      </section>
    </div>

    <template #footer>
      <el-button @click="closeDialog">取消</el-button>
      <el-button type="primary" @click="saveConfig">保存配置</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.api-key-dialog {
  display: grid;
  gap: 14px;
}

.api-key-dialog__section {
  display: grid;
  gap: 12px;
  padding: 14px;
  border: 1px solid var(--df-border);
  border-radius: var(--df-radius-md);
  background: #fbfdff;
}

.api-key-dialog__section h3 {
  margin: 0;
  color: var(--df-text);
  font-size: 15px;
  font-weight: 700;
}

.api-key-dialog__section label {
  display: grid;
  gap: 6px;
}

.api-key-dialog__section label > span {
  color: var(--df-text);
  font-size: 13px;
  font-weight: 600;
}

.api-key-dialog__control {
  width: 100%;
}

.api-key-dialog__section p {
  margin: 0;
  padding: 10px 12px;
  border-radius: var(--df-radius-md);
  background: var(--df-muted);
  color: var(--df-text-secondary);
  font-size: 12px;
  line-height: 1.55;
}
</style>
