<script setup lang="ts">
import CardActionButtons from "@/components/cards/CardActionButtons.vue";
import type { AgentCardAction, ProductTypeDecisionCard } from "@/types/workspace";

defineProps<{
  card: ProductTypeDecisionCard;
  busy: boolean;
}>();

defineEmits<{
  "trigger-action": [action: AgentCardAction];
}>();
</script>

<template>
  <section class="agent-card">
    <h3>{{ card.title }}</h3>
    <dl class="decision-list">
      <div>
        <dt>用户选择</dt>
        <dd>{{ card.userChoice }}</dd>
      </div>
      <div>
        <dt>Agent 判断</dt>
        <dd>{{ card.agentJudgement }}</dd>
      </div>
      <div>
        <dt>建议采用</dt>
        <dd>{{ card.recommendedType }}</dd>
      </div>
    </dl>
    <div class="reason-box">
      <strong>差异原因</strong>
      <ul>
        <li v-for="reason in card.differenceReasons" :key="reason">{{ reason }}</li>
      </ul>
    </div>
    <CardActionButtons
      :actions="card.actions"
      :busy="busy"
      @trigger-action="$emit('trigger-action', $event)"
    />
  </section>
</template>
