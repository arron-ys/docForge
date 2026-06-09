<script setup lang="ts">
import CardActionButtons from "@/components/cards/CardActionButtons.vue";
import type { AgentCardAction, DocPlanConfirmCard } from "@/types/workspace";

defineProps<{
  card: DocPlanConfirmCard;
  busy: boolean;
}>();

defineEmits<{
  "trigger-action": [action: AgentCardAction];
}>();
</script>

<template>
  <section class="agent-card">
    <h3>{{ card.title }}</h3>
    <ol class="section-list">
      <li v-for="section in card.sections" :key="section">{{ section }}</li>
    </ol>
    <CardActionButtons
      :actions="card.actions"
      :busy="busy"
      @trigger-action="$emit('trigger-action', $event)"
    />
  </section>
</template>
