<script setup lang="ts">
import { computed } from "vue";
import { DataAnalysis, Finished, Setting, Warning } from "@element-plus/icons-vue";

import type {
  DiagnosticSummary,
  DocOutputType,
  ProductTypeOption,
  ReferenceStyleStrength,
  WorkspaceSettings,
} from "@/types/workspace";

const props = defineProps<{
  settings: WorkspaceSettings;
  diagnostics: DiagnosticSummary;
}>();

const emit = defineEmits<{
  "update-product-type": [value: ProductTypeOption];
  "update-output-type": [value: DocOutputType];
  "update-reference-strength": [value: ReferenceStyleStrength];
}>();

const productTypeHint = computed({
  get: () => props.settings.productTypeHint,
  set: (value: ProductTypeOption) => emit("update-product-type", value),
});

const docOutputType = computed({
  get: () => props.settings.docOutputType,
  set: (value: DocOutputType) => emit("update-output-type", value),
});

const referenceStyleStrength = computed({
  get: () => props.settings.referenceStyleStrength,
  set: (value: ReferenceStyleStrength) => emit("update-reference-strength", value),
});
</script>

<template>
  <aside class="right-panel" aria-label="运行设置、产品约束和诊断状态">
    <section class="settings-card">
      <div class="settings-card__title">
        <el-icon><Setting /></el-icon>
        产品类型判断参考
      </div>
      <el-radio-group v-model="productTypeHint" class="stacked-radios">
        <el-radio value="saas_web_platform">SaaS / Web 平台</el-radio>
        <el-radio value="ai_platform">AI 平台</el-radio>
        <el-radio value="data_platform">数据平台</el-radio>
        <el-radio value="industrial_software">工业软件</el-radio>
        <el-radio value="tool_software">工具软件</el-radio>
        <el-radio value="agent_decide">让 Agent 根据资料判断</el-radio>
      </el-radio-group>
      <p class="hint-text">
        这里用于提示系统优先考虑的产品类型。选择“让 Agent 根据资料判断”时，系统会在证据充分且无冲突时自动采用推荐结果。
      </p>
    </section>

    <section class="settings-card">
      <div class="settings-card__title">
        <el-icon><Finished /></el-icon>
        输出文档类型
      </div>
      <el-radio-group v-model="docOutputType" class="stacked-radios">
        <el-radio value="user_manual">用户操作手册型软著</el-radio>
        <el-radio value="product_feature_description">产品功能说明型软著</el-radio>
        <el-radio value="technical_design">技术设计说明型软著</el-radio>
      </el-radio-group>
      <p class="hint-text">
        这里用于提示最终文档的写作方向。流程开始后修改可能导致文档策略重新生成。
      </p>
    </section>

    <section class="settings-card">
      <div class="settings-card__title">
        <el-icon><DataAnalysis /></el-icon>
        参考风格强度
      </div>
      <el-segmented
        v-model="referenceStyleStrength"
        :options="[
          { label: '弱参考', value: 'weak' },
          { label: '中参考', value: 'medium' },
          { label: '强参考', value: 'strong' },
        ]"
        block
      />
      <p class="hint-text">
        控制外部参考资料对目录、章节写法和语言风格的影响程度。无论强弱，外部参考资料都不能作为产品事实来源。
      </p>
    </section>

    <section class="settings-card">
      <div class="settings-card__title">
        <el-icon><Warning /></el-icon>
        截图使用策略
      </div>
      <p class="fixed-policy">
        产品截图仅作为配图候选和展示材料，不做 OCR，不作为产品事实证据，
        不用于推断产品功能是否已经实现。
      </p>
    </section>

    <section class="settings-card">
      <div class="settings-card__title">风险策略</div>
      <div class="risk-policy">
        <span><strong>阻塞问题</strong> 必须修复，否则不能导出</span>
        <span><strong>主要风险</strong> 可导出风险版，需人工复核</span>
        <span><strong>轻微问题</strong> 不阻塞导出，但建议处理</span>
        <span><strong>优化建议</strong> 仅作为改进参考</span>
      </div>
    </section>

    <section class="settings-card">
      <div class="settings-card__title">任务推进说明</div>
      <p class="hint-text hint-text--strong">
        右侧设置是写作策略偏好，不是最终 FrozenDocPlan。修改会写入后端；进入冻结或生成阶段后修改会要求确认并重新评估。
      </p>
    </section>

    <section class="settings-card">
      <div class="settings-card__title">当前诊断结果</div>
      <div class="diagnostic-list">
        <div>
          <span>健康状态</span>
          <el-tag type="success">{{ diagnostics.healthLabel }}</el-tag>
        </div>
        <div>
          <span>当前阶段</span>
          <strong>{{ diagnostics.stageLabel }}</strong>
        </div>
        <div>
          <span>下一步建议</span>
          <strong>{{ diagnostics.nextSuggestion }}</strong>
        </div>
      </div>
    </section>
  </aside>
</template>

<style scoped>
.right-panel {
  height: 100%;
  overflow-y: auto;
  background: var(--df-panel);
  padding: 16px;
}

.settings-card {
  padding: 14px;
  border: 1px solid var(--df-border);
  border-radius: var(--df-radius-lg);
  background: var(--df-surface);
  box-shadow: var(--df-shadow-sm);
}

.settings-card + .settings-card {
  margin-top: 12px;
}

.settings-card__title {
  display: flex;
  align-items: center;
  gap: 7px;
  margin-bottom: 12px;
  color: var(--df-text);
  font-size: 14px;
  font-weight: 700;
}

.stacked-radios {
  display: grid;
  gap: 8px;
}

.stacked-radios :deep(.el-radio) {
  height: auto;
  margin-right: 0;
  white-space: normal;
}

.hint-text,
.fixed-policy {
  margin: 12px 0 0;
  padding: 10px 12px;
  border-radius: var(--df-radius-md);
  background: var(--df-muted);
  color: var(--df-text-secondary);
  font-size: 12px;
  line-height: 1.55;
}

.fixed-policy {
  margin-top: 0;
  color: var(--df-text);
}

.hint-text--strong {
  margin-top: 0;
  color: var(--df-text);
}

.risk-policy,
.diagnostic-list {
  display: grid;
  gap: 9px;
}

.risk-policy span {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 9px 10px;
  border-radius: var(--df-radius-md);
  background: var(--df-muted);
  color: var(--df-text-secondary);
  font-size: 12px;
}

.risk-policy strong {
  color: var(--df-text);
}

.diagnostic-list div {
  display: grid;
  gap: 5px;
  padding-bottom: 9px;
  border-bottom: 1px solid var(--df-border);
}

.diagnostic-list div:last-child {
  padding-bottom: 0;
  border-bottom: 0;
}

.diagnostic-list span {
  color: var(--df-text-secondary);
  font-size: 12px;
}

.diagnostic-list strong {
  color: var(--df-text);
  font-size: 13px;
  line-height: 1.4;
}
</style>
