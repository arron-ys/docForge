<script setup lang="ts">
import type { AgentCardAction } from "@/types/workspace";

defineProps<{
  actions: AgentCardAction[];
  busy: boolean;
}>();

defineEmits<{
  "trigger-action": [action: AgentCardAction];
}>();
</script>

<template>
  <div class="card-actions">
    <el-button
      v-for="action in actions"
      :key="action.actionId"
      :type="action.variant === 'primary' ? 'primary' : action.variant === 'danger' ? 'danger' : 'default'"
      :disabled="busy || action.disabled"
      :loading="busy && action.variant === 'primary'"
      @click="$emit('trigger-action', action)"
    >
      {{ action.label }}
    </el-button>
  </div>
</template>
