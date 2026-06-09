<script setup lang="ts">
import { DocumentChecked } from "@element-plus/icons-vue";

import CardActionButtons from "@/components/cards/CardActionButtons.vue";
import type { AgentCardAction, ExportResultCard } from "@/types/workspace";

defineProps<{
  card: ExportResultCard;
  busy: boolean;
}>();

defineEmits<{
  "trigger-action": [action: AgentCardAction];
}>();
</script>

<template>
  <section class="agent-card">
    <h3>{{ card.title }}</h3>
    <div class="export-box">
      <el-icon><DocumentChecked /></el-icon>
      <div>
        <strong>{{ card.artifactName }}</strong>
        <span>{{ card.description }}</span>
      </div>
    </div>
    <CardActionButtons
      :actions="card.actions"
      :busy="busy"
      @trigger-action="$emit('trigger-action', $event)"
    />
  </section>
</template>
