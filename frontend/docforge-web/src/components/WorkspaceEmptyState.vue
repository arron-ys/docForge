<script setup lang="ts">
defineProps<{
  reason: string;
}>();
</script>

<template>
  <main class="empty-page" aria-label="DocForge 工作台空状态">
    <el-card shadow="never" class="empty-card">
      <div class="empty-card__eyebrow">墨衡 DocForge 工作台</div>
      <h1>请先选择一个运行任务</h1>
      <p class="empty-card__reason">{{ reason }}</p>

      <div class="empty-grid">
        <section>
          <strong>API 模式需要 run_id</strong>
          <p>
            请使用后端已创建的任务编号打开工作台，例如
            <code>/?run_id=20260609_143000_ab12</code>。
          </p>
        </section>
        <section>
          <strong>启动 FastAPI</strong>
          <p><code>python -m uvicorn api.main:app --reload</code></p>
        </section>
        <section>
          <strong>切换 mock 模式</strong>
          <p>
            在前端 `.env` 中设置 <code>VITE_DOCFORGE_USE_MOCK=true</code>，即可使用内置演示数据。
          </p>
        </section>
        <section>
          <strong>推荐视口</strong>
          <p>建议使用 1180px 以上宽度查看三栏工作台，避免操作区过窄。</p>
        </section>
      </div>

      <el-alert
        title="这里不是报错页面"
        description="当前页面没有调用无效 API，也不会直接读取后端内部状态文件。选择有效任务后，工作台会通过 FastAPI 加载可展示状态。"
        type="info"
        show-icon
        :closable="false"
      />
    </el-card>
  </main>
</template>

<style scoped>
.empty-page {
  display: grid;
  min-height: 100vh;
  place-items: center;
  padding: 32px;
  background:
    radial-gradient(circle at top left, rgba(37, 99, 235, 0.12), transparent 32%),
    var(--df-bg);
}

.empty-card {
  width: min(820px, calc(100vw - 48px));
  border-radius: 18px;
}

.empty-card :deep(.el-card__body) {
  display: grid;
  gap: 18px;
  padding: 28px;
}

.empty-card__eyebrow {
  color: var(--df-primary);
  font-size: 13px;
  font-weight: 700;
}

.empty-card h1 {
  margin: 0;
  color: var(--df-text);
  font-size: 26px;
}

.empty-card__reason {
  margin: 0;
  color: var(--df-text-secondary);
  font-size: 14px;
  line-height: 1.7;
}

.empty-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.empty-grid section {
  padding: 14px;
  border: 1px solid var(--df-border);
  border-radius: var(--df-radius-lg);
  background: var(--df-panel);
}

.empty-grid strong {
  color: var(--df-text);
  font-size: 14px;
}

.empty-grid p {
  margin: 8px 0 0;
  color: var(--df-text-secondary);
  font-size: 13px;
  line-height: 1.65;
}

code {
  padding: 2px 5px;
  border-radius: 5px;
  background: var(--df-muted);
  color: var(--df-text);
}

@media (max-width: 720px) {
  .empty-grid {
    grid-template-columns: 1fr;
  }
}
</style>
