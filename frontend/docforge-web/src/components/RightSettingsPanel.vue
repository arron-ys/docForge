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
        产品类型提示
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
        这里的选择只作为 Agent 的 prior_hint，不会直接锁死判断。若 Agent
        判断与用户选择冲突，系统会展示差异原因并要求二次确认。只有结构化确认动作才能推进 workflow。
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
        输出类型是写作约束提示，不会让前端直接推进状态。真实生成必须通过后端 Action API。
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
        外部参考软著只影响目录结构、章法、配图方式和语言风格，不作为产品事实来源。
      </p>
    </section>

    <section class="settings-card">
      <div class="settings-card__title">
        <el-icon><Warning /></el-icon>
        截图使用策略
      </div>
      <p class="fixed-policy">
        MVP 阶段截图只作为配图候选和展示材料登记，不做 OCR，不作为强产品事实证据，
        不用于推断当前版本已实现功能。
      </p>
    </section>

    <section class="settings-card">
      <div class="settings-card__title">风险策略</div>
      <div class="risk-policy">
        <span><strong>blocker</strong> 不允许导出</span>
        <span><strong>major</strong> 进入风险版 DOCX</span>
        <span><strong>minor</strong> 允许继续</span>
        <span><strong>suggestion</strong> 仅提示</span>
      </div>
    </section>

    <section class="settings-card">
      <div class="settings-card__title">状态机边界</div>
      <p class="hint-text hint-text--strong">
        右侧设置只影响本地 prior_hint 展示；Vue 不会直接修改后端状态，也不会绕过 ActionGuard。
        所有推进都必须通过中间区域的结构化动作按钮。
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
