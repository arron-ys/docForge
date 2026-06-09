<script setup lang="ts">
import CardActionButtons from "@/components/cards/CardActionButtons.vue";
import type { AgentCardAction, RiskCheckCard } from "@/types/workspace";

defineProps<{
  card: RiskCheckCard;
  busy: boolean;
}>();

defineEmits<{
  "trigger-action": [action: AgentCardAction];
}>();
</script>

<template>
  <section class="agent-card">
    <h3>{{ card.title }}</h3>
    <div class="risk-grid">
      <div class="risk-grid__item risk-grid__item--danger">
        <strong>{{ card.riskSummary.blocker }}</strong>
        <span>blocker：阻塞问题</span>
      </div>
      <div class="risk-grid__item risk-grid__item--warning">
        <strong>{{ card.riskSummary.major }}</strong>
        <span>major：主要风险</span>
      </div>
      <div class="risk-grid__item">
        <strong>{{ card.riskSummary.minor }}</strong>
        <span>minor：轻微问题</span>
      </div>
      <div class="risk-grid__item risk-grid__item--suggestion">
        <strong>{{ card.riskSummary.suggestion }}</strong>
        <span>suggestion：优化建议</span>
      </div>
    </div>
    <p class="risk-conclusion">
      {{ card.riskSummary.conclusion }} Suggestion 仅作为优化建议，不阻塞导出。
    </p>
    <CardActionButtons
      :actions="card.actions"
      :busy="busy"
      @trigger-action="$emit('trigger-action', $event)"
    />
  </section>
</template>
