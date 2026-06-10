<script setup lang="ts">
import { reactive, watch } from "vue";
import { ElMessage } from "element-plus";

import {
  getModelConfig,
  saveModelConfig,
  testEmbeddingConnection,
  testLlmConnection,
} from "@/api/modelConfig";
import type {
  ModelConfigApi,
  ModelProviderConfigApi,
  TestModelConnectionResultApi,
} from "@/api/apiTypes";

type ProviderType = "qwen" | "jina";
type VerifyState = "untested" | "testing" | "passed" | "failed";

interface SectionForm {
  provider: ProviderType;
  model: string;
  baseUrl: string;
  apiKey: string;
  hasSavedApiKey: boolean;
  maskedApiKey: string | null;
  verified: boolean;
  lastVerifiedAt: string | null;
  verifyState: VerifyState;
  verifyMessage: string;
}

const DEFAULT_QWEN_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1";
const DEFAULT_QWEN_MODEL = "qwen-plus";
const DEFAULT_QWEN_API_KEY = "sk-25c6b879b77c4569b8dd4c9f6fe66793";
const DEFAULT_JINA_BASE_URL = "https://api.jina.ai/v1";
const DEFAULT_JINA_MODEL = "jina-embeddings-v3";
const DEFAULT_JINA_API_KEY =
  "jina_2846158833a84d49943a180da948c7a6HaDB-oWbvx7cAs6rH-sP37JRM58z";

const props = defineProps<{
  modelValue: boolean;
}>();

const emit = defineEmits<{
  "update:modelValue": [value: boolean];
  saved: [config: ModelConfigApi];
}>();

const loadingConfig = reactive({ value: false });
const savingConfig = reactive({ value: false });
const testingAll = reactive({ value: false });
const advancedOpen = reactive({
  llm: false,
  embedding: false,
});

const llmForm = reactive<SectionForm>({
  provider: "qwen",
  model: DEFAULT_QWEN_MODEL,
  baseUrl: DEFAULT_QWEN_BASE_URL,
  apiKey: DEFAULT_QWEN_API_KEY,
  hasSavedApiKey: false,
  maskedApiKey: null,
  verified: false,
  lastVerifiedAt: null,
  verifyState: "untested",
  verifyMessage: "",
});

const embeddingForm = reactive<SectionForm>({
  provider: "jina",
  model: DEFAULT_JINA_MODEL,
  baseUrl: DEFAULT_JINA_BASE_URL,
  apiKey: DEFAULT_JINA_API_KEY,
  hasSavedApiKey: false,
  maskedApiKey: null,
  verified: false,
  lastVerifiedAt: null,
  verifyState: "untested",
  verifyMessage: "",
});

function closeDialog() {
  emit("update:modelValue", false);
}

async function loadSavedConfig() {
  loadingConfig.value = true;
  try {
    const config = await getModelConfig();
    applyConfig(config);
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "读取模型配置失败。");
    resetForms();
  } finally {
    loadingConfig.value = false;
  }
}

async function testLlm() {
  if (!llmForm.apiKey.trim() && !llmForm.hasSavedApiKey) {
    setVerifyState(llmForm, "failed", "请先输入 LLM API Key。");
    return;
  }

  setVerifyState(llmForm, "testing", "正在测试连接……");
  try {
    const result = await testLlmConnection({
      provider: llmForm.provider,
      model: llmForm.model.trim(),
      base_url: llmForm.baseUrl.trim(),
      api_key: llmForm.apiKey.trim() || null,
    });
    applyTestResult(llmForm, result);
  } catch (error) {
    setVerifyState(
      llmForm,
      "failed",
      error instanceof Error ? error.message : "LLM 连接测试失败。",
    );
  }
}

async function testEmbedding() {
  if (!embeddingForm.apiKey.trim() && !embeddingForm.hasSavedApiKey) {
    setVerifyState(embeddingForm, "failed", "请先输入 Embedding API Key。");
    return;
  }

  setVerifyState(embeddingForm, "testing", "正在测试连接……");
  try {
    const result = await testEmbeddingConnection({
      provider: embeddingForm.provider,
      model: embeddingForm.model.trim(),
      base_url: embeddingForm.baseUrl.trim(),
      api_key: embeddingForm.apiKey.trim() || null,
    });
    applyTestResult(embeddingForm, result);
  } catch (error) {
    setVerifyState(
      embeddingForm,
      "failed",
      error instanceof Error ? error.message : "Embedding 连接测试失败。",
    );
  }
}

async function testAll() {
  testingAll.value = true;
  try {
    await testLlm();
    await testEmbedding();
  } finally {
    testingAll.value = false;
  }
}

async function saveConfig() {
  savingConfig.value = true;
  try {
    const config = await saveModelConfig({
      llm: {
        provider: llmForm.provider,
        model: llmForm.model.trim(),
        base_url: llmForm.baseUrl.trim(),
        api_key: llmForm.apiKey.trim() || null,
        verified: llmForm.verified,
        last_verified_at: llmForm.lastVerifiedAt,
      },
      embedding: {
        provider: embeddingForm.provider,
        model: embeddingForm.model.trim(),
        base_url: embeddingForm.baseUrl.trim(),
        api_key: embeddingForm.apiKey.trim() || null,
        verified: embeddingForm.verified,
        last_verified_at: embeddingForm.lastVerifiedAt,
      },
    });
    applyConfig(config);
    emit("saved", config);
    ElMessage.success("配置已保存。后端模型调用将优先使用此运行时配置。");
    closeDialog();
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "保存模型配置失败。");
  } finally {
    savingConfig.value = false;
  }
}

function applyConfig(config: ModelConfigApi) {
  applyProviderConfig(llmForm, config.llm, {
    provider: "qwen",
    model: DEFAULT_QWEN_MODEL,
    baseUrl: DEFAULT_QWEN_BASE_URL,
  });
  applyProviderConfig(embeddingForm, config.embedding, {
    provider: "jina",
    model: DEFAULT_JINA_MODEL,
    baseUrl: DEFAULT_JINA_BASE_URL,
  });
}

function applyProviderConfig(
  form: SectionForm,
  config: ModelProviderConfigApi | null,
  defaults: Pick<SectionForm, "provider" | "model" | "baseUrl">,
) {
  form.provider = normalizeProvider(config?.provider, defaults.provider);
  form.model = config?.model || defaults.model;
  form.baseUrl = config?.base_url || defaults.baseUrl;
  form.apiKey = defaultApiKeyForProvider(form.provider);
  form.hasSavedApiKey = Boolean(config?.has_api_key);
  form.maskedApiKey = config?.masked_api_key ?? null;
  form.verified = Boolean(config?.verified);
  form.lastVerifiedAt = config?.last_verified_at ?? null;
  setVerifyState(form, form.verified ? "passed" : "untested", "");
}

function applyTestResult(form: SectionForm, result: TestModelConnectionResultApi) {
  form.verified = result.verified;
  form.lastVerifiedAt = result.last_verified_at;
  setVerifyState(form, result.verified ? "passed" : "failed", result.message);
}

function resetForms() {
  applyConfig({ llm: null, embedding: null });
}

function setVerifyState(form: SectionForm, state: VerifyState, message: string) {
  form.verifyState = state;
  form.verifyMessage = message;
}

function normalizeProvider(value: string | undefined, fallback: ProviderType): ProviderType {
  return value === "qwen" || value === "jina" ? value : fallback;
}

function defaultApiKeyForProvider(provider: ProviderType) {
  return provider === "qwen" ? DEFAULT_QWEN_API_KEY : DEFAULT_JINA_API_KEY;
}

function providerLabel(provider: ProviderType) {
  return provider === "qwen" ? "Qwen" : "Jina";
}

function statusLabel(form: SectionForm) {
  if (form.verifyState === "testing") {
    return "校验中";
  }
  if (form.verifyState === "passed") {
    return "校验通过";
  }
  if (form.verifyState === "failed") {
    return "校验失败";
  }
  if (!form.apiKey.trim() && !form.hasSavedApiKey) {
    return "未配置";
  }
  return "未校验";
}

function verifyTagType(form: SectionForm) {
  if (form.verifyState === "passed") {
    return "success";
  }
  if (form.verifyState === "failed") {
    return "danger";
  }
  if (form.verifyState === "testing") {
    return "warning";
  }
  return "info";
}

function savedKeyText(form: SectionForm, fallbackText: string) {
  if (form.maskedApiKey) {
    return `已保存密钥：${form.maskedApiKey}。留空则继续使用已保存密钥。`;
  }
  return fallbackText;
}

function feedbackVisible(form: SectionForm) {
  return form.verifyState !== "untested" && Boolean(form.verifyMessage);
}

function markChanged(form: SectionForm) {
  if (form.verifyState !== "untested") {
    form.verified = false;
    form.lastVerifiedAt = null;
    setVerifyState(form, "untested", "");
  }
}

function restoreLlmDefaults() {
  llmForm.provider = "qwen";
  llmForm.model = DEFAULT_QWEN_MODEL;
  llmForm.baseUrl = DEFAULT_QWEN_BASE_URL;
  markChanged(llmForm);
}

function restoreEmbeddingDefaults() {
  embeddingForm.provider = "jina";
  embeddingForm.model = DEFAULT_JINA_MODEL;
  embeddingForm.baseUrl = DEFAULT_JINA_BASE_URL;
  markChanged(embeddingForm);
}

watch(
  () => props.modelValue,
  (visible) => {
    if (visible) {
      void loadSavedConfig();
    }
  },
);
</script>

<template>
  <el-dialog
    :model-value="modelValue"
    title="配置模型密钥"
    width="640px"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <div v-loading="loadingConfig.value" class="api-key-dialog">
      <p class="api-key-dialog__intro">
        密钥保存在本机。后端模型调用会优先使用这里的配置；未配置时继续使用 .env。
      </p>

      <section class="api-key-dialog__section">
        <div class="api-key-dialog__section-header">
          <h3>大模型 LLM</h3>
          <div class="api-key-dialog__section-meta">
            <span>{{ providerLabel(llmForm.provider) }}</span>
            <el-tag :type="verifyTagType(llmForm)" effect="plain" size="small">
              {{ statusLabel(llmForm) }}
            </el-tag>
          </div>
        </div>

        <label>
          <span>API Key</span>
          <el-input
            v-model="llmForm.apiKey"
            autocomplete="off"
            class="api-key-dialog__control"
            placeholder="请输入 Qwen API Key"
            type="text"
            @input="markChanged(llmForm)"
          />
        </label>
        <div class="api-key-dialog__saved-key" :class="{ 'is-empty': !llmForm.maskedApiKey }">
          {{ savedKeyText(llmForm, "尚未保存 LLM API Key。") }}
        </div>
        <div
          v-if="feedbackVisible(llmForm)"
          class="api-key-dialog__feedback"
          :class="`is-${llmForm.verifyState}`"
        >
          {{ llmForm.verifyMessage }}
        </div>

        <div class="api-key-dialog__actions">
          <el-button
            :loading="llmForm.verifyState === 'testing'"
            :disabled="loadingConfig.value || testingAll.value"
            @click="testLlm"
          >
            测试 LLM 连接
          </el-button>
          <el-button text type="primary" @click="advancedOpen.llm = !advancedOpen.llm">
            高级设置 {{ advancedOpen.llm ? "˄" : "˅" }}
          </el-button>
        </div>

        <div v-if="advancedOpen.llm" class="api-key-dialog__advanced">
          <label>
            <span>模型服务商</span>
            <div class="api-key-dialog__readonly">Qwen</div>
          </label>
          <label>
            <span>模型名称</span>
            <el-input
              v-model="llmForm.model"
              autocomplete="off"
              class="api-key-dialog__control"
              placeholder="qwen-plus"
              @input="markChanged(llmForm)"
            />
          </label>
          <label>
            <span>BaseURL</span>
            <el-input
              v-model="llmForm.baseUrl"
              autocomplete="off"
              class="api-key-dialog__control"
              placeholder="https://dashscope.aliyuncs.com/compatible-mode/v1"
              @input="markChanged(llmForm)"
            />
          </label>
          <div class="api-key-dialog__advanced-footer">
            <span>通常无需修改。只有使用国际区、代理网关或自定义兼容服务时才需要调整。</span>
            <el-button size="small" @click="restoreLlmDefaults">恢复 Qwen 默认配置</el-button>
          </div>
        </div>
      </section>

      <section class="api-key-dialog__section">
        <div class="api-key-dialog__section-header">
          <h3>向量模型 Embedding</h3>
          <div class="api-key-dialog__section-meta">
            <span>{{ providerLabel(embeddingForm.provider) }}</span>
            <el-tag :type="verifyTagType(embeddingForm)" effect="plain" size="small">
              {{ statusLabel(embeddingForm) }}
            </el-tag>
          </div>
        </div>

        <label>
          <span>API Key</span>
          <el-input
            v-model="embeddingForm.apiKey"
            autocomplete="off"
            class="api-key-dialog__control"
            placeholder="请输入 Jina API Key"
            type="text"
            @input="markChanged(embeddingForm)"
          />
        </label>
        <div
          class="api-key-dialog__saved-key"
          :class="{ 'is-empty': !embeddingForm.maskedApiKey }"
        >
          {{ savedKeyText(embeddingForm, "尚未保存 Embedding API Key。") }}
        </div>
        <div
          v-if="feedbackVisible(embeddingForm)"
          class="api-key-dialog__feedback"
          :class="`is-${embeddingForm.verifyState}`"
        >
          {{ embeddingForm.verifyMessage }}
        </div>

        <div class="api-key-dialog__actions">
          <el-button
            :loading="embeddingForm.verifyState === 'testing'"
            :disabled="loadingConfig.value || testingAll.value"
            @click="testEmbedding"
          >
            测试 Embedding 连接
          </el-button>
          <el-button text type="primary" @click="advancedOpen.embedding = !advancedOpen.embedding">
            高级设置 {{ advancedOpen.embedding ? "˄" : "˅" }}
          </el-button>
        </div>

        <div v-if="advancedOpen.embedding" class="api-key-dialog__advanced">
          <label>
            <span>模型服务商</span>
            <div class="api-key-dialog__readonly">Jina</div>
          </label>
          <label>
            <span>模型名称</span>
            <el-input
              v-model="embeddingForm.model"
              autocomplete="off"
              class="api-key-dialog__control"
              placeholder="jina-embeddings-v3"
              @input="markChanged(embeddingForm)"
            />
          </label>
          <label>
            <span>BaseURL</span>
            <el-input
              v-model="embeddingForm.baseUrl"
              autocomplete="off"
              class="api-key-dialog__control"
              placeholder="https://api.jina.ai/v1"
              @input="markChanged(embeddingForm)"
            />
          </label>
          <div class="api-key-dialog__advanced-footer">
            <span>通常无需修改。</span>
            <el-button size="small" @click="restoreEmbeddingDefaults">
              恢复 Jina 默认配置
            </el-button>
          </div>
        </div>
      </section>
    </div>

    <template #footer>
      <div class="api-key-dialog__footer">
        <el-button
          :loading="testingAll.value"
          :disabled="loadingConfig.value || savingConfig.value"
          @click="testAll"
        >
          测试全部
        </el-button>
        <div>
          <el-button @click="closeDialog">取消</el-button>
          <el-button
            type="primary"
            :loading="savingConfig.value"
            :disabled="loadingConfig.value"
            @click="saveConfig"
          >
            保存配置
          </el-button>
        </div>
      </div>
    </template>
  </el-dialog>
</template>

<style scoped>
.api-key-dialog {
  display: grid;
  gap: 12px;
}

.api-key-dialog__intro {
  margin: 0;
  color: var(--df-text-secondary);
  font-size: 13px;
  line-height: 1.55;
}

.api-key-dialog__section {
  display: grid;
  gap: 10px;
  padding: 14px;
  border: 1px solid var(--df-border);
  border-radius: var(--df-radius-md);
  background: #fbfdff;
}

.api-key-dialog__section-header,
.api-key-dialog__section-meta,
.api-key-dialog__actions,
.api-key-dialog__advanced-footer,
.api-key-dialog__footer {
  display: flex;
  align-items: center;
}

.api-key-dialog__section-header,
.api-key-dialog__advanced-footer,
.api-key-dialog__footer {
  justify-content: space-between;
}

.api-key-dialog__section-header {
  gap: 12px;
}

.api-key-dialog__section-meta {
  flex-shrink: 0;
  gap: 8px;
  color: var(--df-text-secondary);
  font-size: 13px;
  font-weight: 600;
}

.api-key-dialog__section h3 {
  margin: 0;
  color: var(--df-text);
  font-size: 15px;
  font-weight: 700;
}

.api-key-dialog__section label,
.api-key-dialog__advanced {
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

.api-key-dialog__saved-key {
  color: var(--df-text-secondary);
  font-size: 12px;
}

.api-key-dialog__saved-key.is-empty {
  color: var(--df-text-muted);
}

.api-key-dialog__feedback {
  border-radius: var(--df-radius-sm);
  font-size: 12px;
  line-height: 1.5;
}

.api-key-dialog__feedback.is-testing {
  color: #8a5a00;
}

.api-key-dialog__feedback.is-passed {
  color: #2f7d32;
}

.api-key-dialog__feedback.is-failed {
  color: #b42318;
}

.api-key-dialog__actions {
  gap: 10px;
}

.api-key-dialog__advanced {
  margin-top: 2px;
  padding: 12px;
  border: 1px dashed var(--df-border-strong);
  border-radius: var(--df-radius-md);
  background: #ffffff;
}

.api-key-dialog__readonly {
  min-height: 32px;
  padding: 6px 10px;
  border: 1px solid var(--df-border);
  border-radius: var(--df-radius-sm);
  background: var(--df-muted);
  color: var(--df-text-secondary);
  font-size: 13px;
  line-height: 20px;
}

.api-key-dialog__advanced-footer {
  gap: 12px;
  color: var(--df-text-muted);
  font-size: 12px;
  line-height: 1.45;
}

.api-key-dialog__footer {
  width: 100%;
  gap: 12px;
}
</style>
