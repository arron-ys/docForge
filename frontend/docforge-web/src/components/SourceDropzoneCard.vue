<script setup lang="ts">
import { Plus } from "@element-plus/icons-vue";

defineProps<{
  title: string;
  description: string;
  compact?: boolean;
}>();

defineEmits<{
  click: [];
}>();
</script>

<template>
  <button class="source-dropzone" :class="{ 'source-dropzone--compact': compact }" type="button" @click="$emit('click')">
    <span class="source-dropzone__icon">
      <el-icon><Plus /></el-icon>
    </span>
    <strong>{{ title }}</strong>
    <span>{{ description }}</span>
  </button>
</template>

<style scoped>
.source-dropzone {
  display: grid;
  width: 100%;
  min-height: 118px;
  place-items: center;
  gap: 7px;
  padding: 16px 14px;
  text-align: center;
  border: 1px dashed #b8c7dc;
  border-radius: var(--df-radius-md);
  background: rgba(255, 255, 255, 0.68);
  color: var(--df-text-secondary);
  cursor: pointer;
  transition:
    border-color 0.16s ease,
    background-color 0.16s ease,
    box-shadow 0.16s ease;
}

.source-dropzone:hover {
  border-color: var(--df-primary);
  background: #f8fbff;
  box-shadow: var(--df-shadow-sm);
}

.source-dropzone__icon {
  display: grid;
  width: 34px;
  height: 34px;
  place-items: center;
  border-radius: 50%;
  background: #eaf2ff;
  color: var(--df-primary);
  font-size: 18px;
}

.source-dropzone strong {
  color: var(--df-text);
  font-size: 13px;
  line-height: 1.35;
}

.source-dropzone span:last-child {
  max-width: 240px;
  font-size: 12px;
  line-height: 1.5;
}

.source-dropzone--compact {
  min-height: 104px;
  gap: 6px;
  padding: 14px 12px;
}

.source-dropzone--compact .source-dropzone__icon {
  width: 30px;
  height: 30px;
  font-size: 16px;
}
</style>
