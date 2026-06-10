# 墨衡 DocForge Web

墨衡 DocForge Web 是 v0.1 的正式产品入口：Vue3 三栏式 Agent 工作台。它通过 HTTP / REST 调用 FastAPI，不直接调用 Agent，不直接读取后端内部状态文件，也不直接改写后端任务状态。

Streamlit 入口仍然保留，但只作为开发调试入口 / 旧 Demo 入口。

## 技术栈

Vue 3 / Vite / TypeScript / Element Plus / Pinia / Vue Router / Axios / pnpm

## 当前状态

当前状态为 DocForge v0.1 正式入口。工作台已接入真实 FastAPI，同时保留 mock 模式用于界面检查和开发兜底。

## 前端环境准备

前端不是 Python `.venv` 管理。Vue 3 / Vite 需要 Node.js 工具链：

- Node.js：运行前端构建和开发服务。
- npm：Node.js 自带的包管理器。
- Corepack：Node.js 附带的包管理器代理，用于启用 pnpm。
- pnpm：本项目使用的前端包管理器。

`pnpm` 是 Node.js 包管理器，不应该安装到 Python `.venv`。Python `.venv` 只用于后端 Python 依赖。

macOS 推荐安装系统 Node.js，例如：

```bash
brew install node
```

安装 Node.js 后启用 pnpm：

```bash
corepack enable
corepack prepare pnpm@latest --activate
```

检查工具链：

```bash
node -v
npm -v
corepack -v
pnpm -v
```

也可以从项目根目录运行：

```bash
scripts/check_frontend_env.sh
```

或在前端目录运行：

```bash
cd frontend/docforge-web
node scripts/check-env.mjs
```

不要使用临时 Node 或 `/private/tmp` 下的 Node 启动长期开发环境；Codex 托管的临时 Node 有时会导致 Vite / Rollup native 包加载失败。

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

如果 Rollup native 包报错，通常是 Node / pnpm 安装或 `node_modules` 状态不稳定。先使用系统 Node.js + Corepack，然后清理并重装：

```bash
rm -rf node_modules dist .vite .cache tsconfig.tsbuildinfo
pnpm install
pnpm dev
```

访问：

```text
http://127.0.0.1:5173/
```

直接打开根地址时，前端会通过 FastAPI 自动进入最近更新的本地任务；如果还没有任何任务，会自动创建一个新任务，并把地址栏同步为带 `run_id` 的工作台地址。

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

- 外部参考资料
- 自有产品资料
- 生成产物 / 导出历史

外部参考资料支持多文件紧凑列表展示；自有产品资料内部按“产品文档 / 产品截图”二级分组展示。产品截图不再作为左侧一级区块。

中间：Agent 工作区。

- Agent 消息
- 结构化卡片
- 当前主操作
- 本地备注输入
- 错误提示
- 导出结果

自由文本输入仅记录为当前页面备注，当前版本不会把备注内容提交给后端生成流程。任务推进仍通过当前主操作和结构化按钮完成。

右侧：运行设置与诊断区。

- 产品类型判断参考
- 输出文档类型
- 参考风格强度
- 截图策略
- 风险策略
- 当前诊断

右侧设置只作为当前页面的写作参考，不会锁死 Agent 判断，也不会直接推进任务。需要推进任务时，请使用中间区域的当前主操作。

顶部右侧提供“配置密钥”入口。该弹窗已经接入 FastAPI 运行时模型配置：

- 默认只展示 Qwen API Key 和 Jina API Key 两个核心输入框。
- 模型名称、BaseURL 和服务商状态收进“高级设置”，通常不需要修改。
- 需要使用国际区、代理网关或自定义兼容服务时，再展开高级设置修改 BaseURL。
- 支持分别测试 LLM / Embedding 连接，也支持“测试全部”。
- 保存配置不要求校验通过；测试连接只用于快速确认 Key、BaseURL 和模型名称是否可用。
- 保存后写入本机用户目录的运行时配置文件，刷新页面和重启服务后仍可读取。
- 接口响应只返回 `has_api_key` 和 `masked_api_key`，不会回显完整 API Key。

运行时配置优先级高于根目录 `.env`；没有运行时配置时，后端继续 fallback 到 `.env`。

## 资料上传

工作台在 UI 上提供两个一级上传类型：

- 外部参考资料：只用于目录、章法、语言风格和配图方式，不作为产品事实来源。
- 自有产品资料：支持产品文档和产品截图。文档可作为产品事实依据；截图仅作为展示材料和配图候选。

产品截图在 v0.1 不做 OCR、不做视觉模型解析、不作为产品事实证据、不用于推断当前版本已实现功能。

## 任务推进

工作台通过后端接口推进当前主操作。FastAPI 会进行任务状态校验，并阻止前端跳过必要流程。

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

本前端不引入 WebSocket/SSE，不包含登录、权限或多租户。mock 模式只验证界面，不代表真实生成结果；真实任务请使用 FastAPI 模式，根地址会自动选择或创建运行任务。

v0.1 本地单机版的模型配置保存到本机用户目录：

- macOS / Linux：`~/.docforge/model_config.json`
- Windows：`%APPDATA%/DocForge/model_config.json`

该文件允许本地明文保存 API Key，只用于开发和单机试用，不是生产级密钥托管方案。当前前端单机测试版会用明文输入框方便核对 Key；不要把真实 API Key、运行时配置文件或 `.env` 提交到 git。
