<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import { getModelConfig } from "@/api/modelConfig";
import ApiKeyConfigDialog from "@/components/ApiKeyConfigDialog.vue";
import SourceUploadDialog from "@/components/SourceUploadDialog.vue";
import WorkspaceEmptyState from "@/components/WorkspaceEmptyState.vue";
import WorkspaceLayout from "@/layouts/WorkspaceLayout.vue";
import { useMockApi } from "@/api/httpClient";
import { useWorkspaceStore } from "@/stores/workspace";
import type { SourceUploadType } from "@/api/sourceApi";
import type { ModelConfigApi } from "@/api/apiTypes";
import type { AgentCardAction, WorkspaceAction } from "@/types/workspace";

const workspaceStore = useWorkspaceStore();
const route = useRoute();
const router = useRouter();
const workspace = computed(() => workspaceStore.workspace);
const uploadDialogVisible = ref(false);
const activeUploadType = ref<SourceUploadType>("reference");
const apiKeyDialogVisible = ref(false);
const modelConfig = ref<ModelConfigApi | null>(null);
const apiKeyConfigured = computed(
  () =>
    Boolean(modelConfig.value?.llm?.has_api_key) &&
    Boolean(modelConfig.value?.embedding?.has_api_key),
);

const queryRunId = computed(() => {
  const value = route.query.run_id;
  return Array.isArray(value) ? value[0] ?? null : value ?? null;
});

watch(
  queryRunId,
  async (runId) => {
    if (runId && workspaceStore.runId === runId && workspaceStore.workspace) {
      return;
    }

    const loadedRunId = await workspaceStore.loadInitialWorkspace(runId);
    if (!runId && loadedRunId) {
      await router.replace({
        path: route.path,
        query: { ...route.query, run_id: loadedRunId },
      });
    }
  },
  { immediate: true },
);

function handleTriggerAction(action: AgentCardAction | WorkspaceAction) {
  if (action.actionType === "open_upload" || action.actionType === "open_upload_mock") {
    openUploadDialog("reference");
    return;
  }
  void workspaceStore.triggerAction(action);
}

function openUploadDialog(uploadType: SourceUploadType) {
  activeUploadType.value = uploadType;
  uploadDialogVisible.value = true;
}

async function submitUpload(payload: { uploadType: SourceUploadType; file: File }) {
  const succeeded = await workspaceStore.uploadSourceFile(payload.uploadType, payload.file);
  if (succeeded) {
    uploadDialogVisible.value = false;
  }
}

async function refreshModelConfig() {
  if (useMockApi) {
    return;
  }
  try {
    modelConfig.value = await getModelConfig();
  } catch {
    modelConfig.value = null;
  }
}

onMounted(() => {
  void refreshModelConfig();
});
</script>

<template>
  <template v-if="workspace">
    <WorkspaceLayout
      :workspace="workspace"
      :loading="workspaceStore.loading"
      :sending="workspaceStore.isBusy"
      :downloading-artifact-id="workspaceStore.downloadingArtifactId"
      :api-key-configured="apiKeyConfigured"
      @send-message="workspaceStore.sendMessage"
      @trigger-action="handleTriggerAction"
      @select-source="workspaceStore.explainSource"
      @open-upload="openUploadDialog"
      @open-api-key-config="apiKeyDialogVisible = true"
      @download-artifact="workspaceStore.downloadArtifact"
      @update-product-type="workspaceStore.updateProductTypeHint"
      @update-output-type="workspaceStore.updateDocOutputType"
      @update-reference-strength="workspaceStore.updateReferenceStyleStrength"
    />
    <SourceUploadDialog
      v-model="uploadDialogVisible"
      :uploading="workspaceStore.uploading"
      :disabled="!workspaceStore.runId"
      :active-upload-type="activeUploadType"
      @submit="submitUpload"
    />
    <ApiKeyConfigDialog
      v-model="apiKeyDialogVisible"
      @saved="modelConfig = $event"
    />
  </template>
  <div v-else-if="workspaceStore.emptyReason" class="workspace-loading">
    <WorkspaceEmptyState :reason="workspaceStore.emptyReason" />
  </div>
  <div v-else class="workspace-loading">
    <el-card shadow="never" class="workspace-loading__card">
      <el-skeleton :rows="6" animated />
    </el-card>
  </div>
</template>

<style scoped>
.workspace-loading {
  display: grid;
  min-height: 100vh;
  place-items: center;
  background: var(--df-bg);
}

.workspace-loading__card {
  width: min(560px, calc(100vw - 48px));
}

</style>
