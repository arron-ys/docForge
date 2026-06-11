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
    <p v-if="card.summary">{{ card.summary }}</p>
    <dl v-if="card.payload" class="decision-details">
      <div>
        <dt>Agent 推荐产品类型</dt>
        <dd>{{ card.payload.recommendedProductType || "待确认" }}</dd>
      </div>
      <div>
        <dt>你的当前选择</dt>
        <dd>{{ card.payload.userSelectedProductType || "让 Agent 根据资料判断" }}</dd>
      </div>
      <div>
        <dt>输出文档类型</dt>
        <dd>{{ card.payload.selectedDocType || card.payload.recommendedDocType }}</dd>
      </div>
      <div>
        <dt>参考风格强度</dt>
        <dd>{{ card.payload.referenceStyleStrength }}</dd>
      </div>
    </dl>
    <p v-if="card.payload?.evidenceBoundary" class="boundary-note">
      {{ card.payload.evidenceBoundary }}
    </p>
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

<style scoped>
.decision-details {
  display: grid;
  gap: 8px;
}

.decision-details div {
  display: grid;
  grid-template-columns: 140px minmax(0, 1fr);
  gap: 12px;
}

.decision-details dt {
  color: var(--df-text-secondary);
}

.decision-details dd {
  margin: 0;
  font-weight: 600;
}

.boundary-note {
  color: var(--df-text-secondary);
  font-size: 12px;
}
</style>
