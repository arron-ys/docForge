<script setup lang="ts">
import DocPlanConfirmCard from "@/components/cards/DocPlanConfirmCard.vue";
import ExportResultCard from "@/components/cards/ExportResultCard.vue";
import ProductTypeDecisionCard from "@/components/cards/ProductTypeDecisionCard.vue";
import RiskCheckCard from "@/components/cards/RiskCheckCard.vue";
import SourceReceivedCard from "@/components/cards/SourceReceivedCard.vue";
import type { AgentCardAction, AgentMessage } from "@/types/workspace";

defineProps<{
  message: AgentMessage;
  busy: boolean;
}>();

defineEmits<{
  "trigger-action": [action: AgentCardAction];
}>();

</script>

<template>
  <article class="message" :class="`message--${message.role}`">
    <div class="message__avatar">
      {{ message.role === "agent" ? "墨" : message.role === "system" ? "!" : "你" }}
    </div>
    <div class="message__body">
      <div class="message__meta">
        <strong>
          {{ message.role === "agent" ? "DocForge Agent" : message.role === "system" ? "系统提示" : "你" }}
        </strong>
        <span>{{ message.createdAtLabel }}</span>
      </div>
      <p>{{ message.content }}</p>
      <template v-if="message.card">
        <SourceReceivedCard
          v-if="message.card.cardType === 'source_received'"
          :card="message.card"
          :busy="busy"
          @trigger-action="$emit('trigger-action', $event)"
        />
        <ProductTypeDecisionCard
          v-else-if="message.card.cardType === 'product_type_decision'"
          :card="message.card"
          :busy="busy"
          @trigger-action="$emit('trigger-action', $event)"
        />
        <DocPlanConfirmCard
          v-else-if="message.card.cardType === 'doc_plan_confirm'"
          :card="message.card"
          :busy="busy"
          @trigger-action="$emit('trigger-action', $event)"
        />
        <RiskCheckCard
          v-else-if="message.card.cardType === 'risk_check'"
          :card="message.card"
          :busy="busy"
          @trigger-action="$emit('trigger-action', $event)"
        />
        <ExportResultCard
          v-else-if="message.card.cardType === 'export_result'"
          :card="message.card"
          :busy="busy"
          @trigger-action="$emit('trigger-action', $event)"
        />
      </template>
    </div>
  </article>
</template>

<style scoped>
.message {
  display: grid;
  grid-template-columns: 34px minmax(0, 1fr);
  max-width: 840px;
  margin: 0 auto 16px;
  gap: 10px;
}

.message--user {
  grid-template-columns: minmax(0, 1fr) 34px;
}

.message--user .message__avatar {
  grid-column: 2;
  grid-row: 1;
  background: var(--df-text);
}

.message--user .message__body {
  grid-column: 1;
  grid-row: 1;
  justify-self: end;
  background: var(--df-user-bubble);
}

.message--user .message__meta {
  justify-content: flex-end;
}

.message--system .message__avatar {
  background: #d97706;
}

.message--system .message__body {
  background: #fff7ed;
  border-color: #fed7aa;
}

.message__avatar {
  display: grid;
  width: 34px;
  height: 34px;
  place-items: center;
  border-radius: 50%;
  background: var(--df-primary);
  color: #fff;
  font-size: 13px;
  font-weight: 700;
}

.message__body {
  min-width: 0;
  padding: 13px 14px;
  border: 1px solid var(--df-border);
  border-radius: var(--df-radius-lg);
  background: var(--df-surface);
  box-shadow: var(--df-shadow-sm);
}

.message__meta {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
  color: var(--df-text-secondary);
  font-size: 12px;
}

.message__meta strong {
  color: var(--df-text);
  font-weight: 700;
}

.message__body p {
  margin: 0;
  color: var(--df-text);
  font-size: 14px;
  line-height: 1.65;
  white-space: pre-wrap;
}
</style>
