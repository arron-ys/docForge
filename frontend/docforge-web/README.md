# 墨衡 DocForge Web

墨衡 DocForge Web 是 v0.1 的正式产品入口：Vue3 三栏式 Agent 工作台。它通过 HTTP / REST 调用 FastAPI，不直接调用 Agent，不直接读取后端内部状态文件，也不直接修改 workflow。

Streamlit 入口仍然保留，但只作为开发调试入口 / 旧 Demo 入口。

## 技术栈

Vue 3 / Vite / TypeScript / Element Plus / Pinia / Vue Router / Axios / pnpm

## 当前状态

当前状态为 DocForge v0.1 正式入口。工作台已接入真实 FastAPI，同时保留 mock 模式用于界面检查和开发兜底。

## 启动方式

启动 FastAPI：

```bash
python -m uvicorn api.main:app --reload
```

启动前端：

```bash
cd frontend/docforge-web
pnpm install
pnpm dev
```

访问：

```text
http://127.0.0.1:5173/
```

使用真实任务时需要 URL 携带 `run_id`：

```text
http://127.0.0.1:5173/?run_id=20260609_143000_ab12
```

如果没有 `run_id`，页面会显示空状态，提示如何进入任务。

## API / Mock 配置

复制 `.env.example` 为本地 `.env`：

```bash
cd frontend/docforge-web
cp .env.example .env
```

真实 API 模式：

```dotenv
VITE_DOCFORGE_API_BASE_URL=http://127.0.0.1:8000/api
VITE_DOCFORGE_USE_MOCK=false
```

mock 模式：

```dotenv
VITE_DOCFORGE_USE_MOCK=true
```

- `VITE_DOCFORGE_USE_MOCK=false`：使用真实 FastAPI，支持加载 WorkspaceView、上传资料、执行 action 和下载 DOCX。
- `VITE_DOCFORGE_USE_MOCK=true`：使用内置 mock 数据，不调用后端，只用于检查界面，不代表真实生成结果。

## 三栏工作台

左侧：资料与项目上下文。

- 当前任务
- 参考资料
- 自有资料
- 产品截图
- 导出历史

中间：Agent 对话区。

- Agent 消息
- 结构化卡片
- 当前主操作
- 错误提示
- 导出结果

右侧：运行设置与诊断区。

- 产品类型 `prior_hint`
- 输出文档类型
- 参考风格强度
- 截图策略
- 风险策略
- 当前诊断

右侧设置只是 `prior_hint`，不会锁死 Agent 判断。只有结构化 action 才会推进 workflow，前端不会直接修改 workflow 状态。

## 资料上传

工作台通过 FastAPI 上传三类资料：

- 外部参考软著：`reference_style / style_only`，只用于目录、章法、语言风格和配图方式，不作为产品事实来源。
- 自有产品资料：`product_evidence / factual_evidence`，可作为产品事实来源。
- 产品截图：`product_evidence / display_material_only`，仅作为展示材料登记和配图候选。

截图在 v0.1 不做 OCR、不做视觉模型解析、不作为强产品事实证据、不用于推断当前版本已实现功能。

## Action

工作台通过后端 Action API 推进当前主操作。FastAPI 会进行 action 状态校验，并阻止前端绕过 workflow。

当前状态不允许执行某个 action 时，前端应展示用户可读错误，例如“当前状态还不能执行该操作，请先完成上一阶段。”`confirm-product-type` / `confirm-doc-plan` 的完整后端确认流仍待后续版本补齐。

## Artifact 下载

可下载产物通过 Artifact API 下载：

```text
/api/artifacts/{artifact_id}/download
```

v0.1 的正式用户产物是 DOCX：

- `软件著作权文档.docx`
- `软件著作权文档_风险版.docx`

`state.json`、`evidence_map`、审计报告、质量门禁报告和 manifest 是内部产物，不作为用户下载物。

## 目录结构

- `src/types`：前端数据契约与 API 类型。
- `src/mock`：集中管理工作台 mock 数据。
- `src/api`：FastAPI client、mock client、snake_case 到 camelCase mapper。
- `src/stores`：Pinia workspace 状态和交互动作。
- `src/components`：三栏工作台组件和结构化 Agent 卡片。
- `src/layouts`：工作台布局。
- `src/views`：路由页面入口。

## UX 验收与本地试用

- Sprint 4 UX 验收清单见 [UX_ACCEPTANCE.md](./UX_ACCEPTANCE.md)。
- 本地试用手册见 [../../docs/本地试用操作手册.md](../../docs/本地试用操作手册.md)。

## 边界说明

本前端不引入 WebSocket/SSE，不包含登录、权限或多租户。mock 模式只验证界面，不代表真实生成结果；真实任务请使用 FastAPI 模式并携带 `run_id`。
