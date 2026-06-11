# 本地 E2E 验收

本文档用于 DocForge v0.1 本地开发验收。正式产品入口是 Vue3 三栏式 Agent 工作台。

`app/main.py` 仅保留为 Python 启动入口，不是独立产品 UI。

## 启动服务

启动 FastAPI：

```bash
.venv/bin/python -m uvicorn api.main:app --reload
```

健康检查：

```text
http://127.0.0.1:8000/healthz
```

启动 Vue 前端：

```bash
cd frontend/docforge-web
pnpm install
pnpm dev
```

访问：

```text
http://127.0.0.1:5173/
```

使用真实任务时：

```text
http://127.0.0.1:5173/?run_id=<真实任务编号>
```

可选通过 Python 入口启动当前开发链路：

```bash
.venv/bin/python app/main.py
```

## 样例工程闭环

1. 启动 FastAPI。
2. 启动 Vue 前端。
3. 运行 `./scripts/import_sample_project.py`。
4. 读取输出中的 `run_id`。
7. 打开 Vue 工作台：`http://127.0.0.1:5173/?run_id=<run_id>`。
8. 查看左侧资料、中央 Agent 消息和右侧运行设置 / 诊断。
9. 触发当前主操作。
10. 终态下载 DOCX 或风险版 DOCX。

Vue 工作台应展示用户可读状态和下一步建议，不应暴露内部路径、Python trace 或内部 artifact 详情。

## 命令行验收

```bash
scripts/test_quick.sh
scripts/test_smoke.sh
scripts/test_integration.sh
```

完整回归：

```bash
scripts/test_full.sh
scripts/test_frontend.sh
git diff --check
```

如果需要补充 Python 静态检查，可额外运行：

```bash
.venv/bin/ruff check .
.venv/bin/python -m compileall docforge_core tests app api
git diff --check
```

## 交付边界

普通用户只下载 DOCX。以下内部文件不作为正式下载物：

- `state.json`
- `evidence_map.json`
- `audit_report_v*.json`
- `quality_gate_report_v*.json`
- `revision_trace_v*.json`
- `export_manifest.json`

v0.1 不做截图 OCR、截图绑定、视觉模型解析、PDF 导出或 Markdown 导出。
