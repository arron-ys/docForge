<script setup lang="ts">
import AgentChatPanel from "@/components/AgentChatPanel.vue";
import LeftContextPanel from "@/components/LeftContextPanel.vue";
import RightSettingsPanel from "@/components/RightSettingsPanel.vue";
import TopBar from "@/components/TopBar.vue";
import type { SourceUploadType } from "@/api/sourceApi";
import type {
  AgentCardAction,
  DocOutputType,
  ExportArtifact,
  ProductTypeOption,
  ReferenceStyleStrength,
  SourceItem,
  WorkspaceAction,
  WorkspaceState,
} from "@/types/workspace";

defineProps<{
  workspace: WorkspaceState;
  loading: boolean;
  sending: boolean;
  downloadingArtifactId: string | null;
  apiKeyConfigured: boolean;
}>();

defineEmits<{
  "send-message": [content: string];
  "trigger-action": [action: AgentCardAction | WorkspaceAction];
  "select-source": [source: SourceItem];
  "open-upload": [uploadType: SourceUploadType];
  "open-api-key-config": [];
  "download-artifact": [artifact: ExportArtifact];
  "update-product-type": [value: ProductTypeOption];
  "update-output-type": [value: DocOutputType];
  "update-reference-strength": [value: ReferenceStyleStrength];
}>();

function findUploadAction(actions: WorkspaceAction[]): WorkspaceAction | undefined {
  return actions.find((action) =>
    ["open_upload", "open_upload_mock"].includes(action.actionType),
  );
}
</script>

<template>
  <div class="workspace-shell">
    <div class="workspace-width-warning">
      建议使用 1180px 以上宽度查看 DocForge 三栏工作台。
    </div>
    <TopBar
      :run="workspace.runSummary"
      :primary-action="workspace.primaryAction"
      :api-key-configured="apiKeyConfigured"
      @open-api-key-config="$emit('open-api-key-config')"
    />
    <main class="workspace-layout" aria-label="墨衡 DocForge Agent 工作台">
      <LeftContextPanel
        :sources="workspace.sources"
        :export-artifacts="workspace.exportArtifacts"
        :downloading-artifact-id="downloadingArtifactId"
        :api-key-configured="apiKeyConfigured"
        @select-source="$emit('select-source', $event)"
        @open-upload="$emit('open-upload', $event)"
        @download-artifact="$emit('download-artifact', $event)"
      />
      <AgentChatPanel
        :messages="workspace.messages"
        :primary-action="workspace.primaryAction"
        :upload-action="findUploadAction(workspace.availableActions)"
        :sending="sending"
        @send-message="$emit('send-message', $event)"
        @trigger-action="$emit('trigger-action', $event)"
      />
      <RightSettingsPanel
        :settings="workspace.settings"
        :diagnostics="workspace.diagnostics"
        @update-product-type="$emit('update-product-type', $event)"
        @update-output-type="$emit('update-output-type', $event)"
        @update-reference-strength="$emit('update-reference-strength', $event)"
      />
    </main>
  </div>
</template>

<style scoped>
.workspace-shell {
  display: flex;
  flex-direction: column;
  height: 100vh;
  min-width: 1180px;
  overflow: hidden;
  background: var(--df-bg);
}

.workspace-width-warning {
  display: none;
  padding: 8px 12px;
  border-bottom: 1px solid var(--df-warning-border);
  background: #fff7ed;
  color: #9a3412;
  font-size: 12px;
  text-align: center;
}

.workspace-layout {
  display: grid;
  grid-template-columns: 280px minmax(420px, 1fr) 360px;
  gap: 1px;
  height: calc(100vh - 56px);
  overflow: hidden;
  background: var(--df-border);
}

@media (max-width: 1179px) {
  .workspace-shell {
    min-width: 0;
  }

  .workspace-width-warning {
    display: block;
  }

  .workspace-layout {
    min-width: 1180px;
    height: calc(100vh - 89px);
    overflow: hidden;
  }
}
</style>
