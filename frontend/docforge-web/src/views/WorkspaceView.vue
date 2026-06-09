<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useRoute } from "vue-router";

import SourceUploadDialog from "@/components/SourceUploadDialog.vue";
import WorkspaceEmptyState from "@/components/WorkspaceEmptyState.vue";
import WorkspaceLayout from "@/layouts/WorkspaceLayout.vue";
import { useWorkspaceStore } from "@/stores/workspace";
import type { SourceUploadType } from "@/api/sourceApi";
import type { AgentCardAction, WorkspaceAction } from "@/types/workspace";

const workspaceStore = useWorkspaceStore();
const route = useRoute();
const workspace = computed(() => workspaceStore.workspace);
const uploadDialogVisible = ref(false);

const queryRunId = computed(() => {
  const value = route.query.run_id;
  return Array.isArray(value) ? value[0] ?? null : value ?? null;
});

watch(
  queryRunId,
  (runId) => {
    void workspaceStore.loadWorkspace(runId);
  },
  { immediate: true },
);

function handleTriggerAction(action: AgentCardAction | WorkspaceAction) {
  if (action.actionType === "open_upload" || action.actionType === "open_upload_mock") {
    uploadDialogVisible.value = true;
    return;
  }
  void workspaceStore.triggerAction(action);
}

async function submitUpload(payload: { uploadType: SourceUploadType; file: File }) {
  const succeeded = await workspaceStore.uploadSourceFile(payload.uploadType, payload.file);
  if (succeeded) {
    uploadDialogVisible.value = false;
  }
}
</script>

<template>
  <template v-if="workspace">
    <WorkspaceLayout
      :workspace="workspace"
      :loading="workspaceStore.loading"
      :sending="workspaceStore.isBusy"
      :downloading-artifact-id="workspaceStore.downloadingArtifactId"
      @send-message="workspaceStore.sendMessage"
      @trigger-action="handleTriggerAction"
      @select-source="workspaceStore.explainSource"
      @download-artifact="workspaceStore.downloadArtifact"
      @update-product-type="workspaceStore.updateProductTypeHint"
      @update-output-type="workspaceStore.updateDocOutputType"
      @update-reference-strength="workspaceStore.updateReferenceStyleStrength"
    />
    <SourceUploadDialog
      v-model="uploadDialogVisible"
      :uploading="workspaceStore.uploading"
      :disabled="!workspaceStore.runId"
      @submit="submitUpload"
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
