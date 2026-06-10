<script setup lang="ts">
defineProps<{
  reason: string;
}>();
</script>

<template>
  <main class="empty-page" aria-label="DocForge 工作台空状态">
    <el-card shadow="never" class="empty-card">
      <div class="empty-card__eyebrow">墨衡 DocForge 工作台</div>
      <h1>暂时无法打开工作台</h1>
      <p class="empty-card__reason">{{ reason }}</p>

      <div class="empty-grid">
        <section>
          <strong>自动任务入口</strong>
          <p>
            直接打开 <code>/</code> 时，前端会通过 FastAPI 自动进入最新任务；没有任务时会自动创建一个新任务。
          </p>
        </section>
        <section>
          <strong>一键启动</strong>
          <p><code>scripts/dev.sh</code></p>
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
        description="当前页面没有读取后端内部状态文件。工作台只能通过 FastAPI 加载任务；如果 FastAPI 未启动或任务加载失败，会显示这类恢复提示。"
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
