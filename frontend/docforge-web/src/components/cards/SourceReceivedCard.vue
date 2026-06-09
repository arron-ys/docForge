<script setup lang="ts">
import CardActionButtons from "@/components/cards/CardActionButtons.vue";
import type { AgentCardAction, SourceReceivedCard } from "@/types/workspace";

defineProps<{
  card: SourceReceivedCard;
  busy: boolean;
}>();

defineEmits<{
  "trigger-action": [action: AgentCardAction];
}>();
</script>

<template>
  <section class="agent-card">
    <h3>{{ card.title }}</h3>
    <div class="metric-grid">
      <div>
        <strong>{{ card.counts.externalReferences }}</strong>
        <span>外部参考资料</span>
      </div>
      <div>
        <strong>{{ card.counts.productMaterials }}</strong>
        <span>自有产品资料</span>
      </div>
      <div>
        <strong>{{ card.counts.screenshots }}</strong>
        <span>产品截图</span>
      </div>
    </div>
    <p>下一步：{{ card.nextStepLabel }}</p>
    <CardActionButtons
      :actions="card.actions"
      :busy="busy"
      @trigger-action="$emit('trigger-action', $event)"
    />
  </section>
</template>
