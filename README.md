# 墨衡 DocForge

墨衡 DocForge 是一个面向软件著作权文档生成的多智能体文档生产系统。当前版本为 **v0.1**，正式产品入口是 **Vue3 三栏式 Agent 工作台**，路径为 `frontend/docforge-web`。

Streamlit 入口仍然保留，但只作为开发调试入口 / 旧 Demo 入口，不再是 v0.1 正式产品入口。

## 当前 v0.1 架构

```text
用户浏览器
  ↓
Vue3 三栏式 Agent 工作台
  ↓ HTTP / REST
FastAPI API 层
  ↓ Python 调用
docforge_core 核心业务模块
  ↓
本地文件系统 / Qdrant Local / 外部 LLM API
```

职责边界：

- Vue 工作台负责资料上下文展示、Agent 对话区、运行设置、上传资料、触发结构化 action、展示诊断状态、下载 DOCX、展示错误和下一步建议。
- FastAPI 负责 WorkspaceView API、Source Upload API、Run Action API、Diagnostics API、Artifact Download API、用户可读状态映射、action 状态校验，并防止前端绕过 workflow。
- `docforge_core` 负责 workflow 状态机、Agent / Service、Evidence、FrozenDocPlan、QualityGate、DOCX 导出、Qdrant 检索和状态持久化。
- Streamlit 负责开发调试和旧 Demo 验证，不作为正式入口。

## 启动方式

前后端使用两套工具链：

- Python `.venv` 只管理后端依赖。
- Node.js / npm / pnpm 管理 Vue 前端依赖。
- `pnpm` 是 Node.js 包管理器，不应安装到 Python `.venv`。

一键启动 FastAPI 后端和 Vue 前端：

```bash
scripts/dev.sh
```

这个脚本会自动完成：

- 检查前端 Node.js / npm / Corepack / pnpm 工具链。
- 如果项目根目录没有 `.venv`，自动创建后端 Python 虚拟环境。
- 后端缺少 FastAPI / Uvicorn 等依赖时，自动执行 `pip install -e .`。
- 前端依赖不存在或 `package.json` / `pnpm-lock.yaml` 有更新时，自动执行 `pnpm install`。
- 同时启动 FastAPI 和 Vue Vite dev server。
- 按 `Ctrl-C` 时同时停止前后端进程。

启动后访问：

```text
http://127.0.0.1:5173/
```

直接打开根地址时，前端会通过 FastAPI 自动进入最近更新的本地任务；如果还没有任何任务，会自动创建一个新任务，并把地址栏同步为带 `run_id` 的工作台地址。

可选端口配置：

```bash
DOCFORGE_BACKEND_PORT=8001 DOCFORGE_FRONTEND_PORT=5174 scripts/dev.sh
```

### 手动启动

检查前端工具链：

```bash
scripts/check_frontend_env.sh
```

如果 `pnpm` 不存在，先安装系统 Node.js，并启用 Corepack：

```bash
corepack enable
corepack prepare pnpm@latest --activate
```

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

正式访问：

```text
http://127.0.0.1:5173/
```

可选启动 Streamlit 调试入口：

```bash
streamlit run app/main.py
```

## 本地试用

第一次本地试用请先阅读 [docs/本地试用操作手册.md](docs/本地试用操作手册.md)。

v0.1 真实 API 模式需要同时启动 FastAPI 和 Vue 前端。打开 `http://127.0.0.1:5173/` 后，Vue 工作台会自动选择最近更新的本地任务；没有任务时会通过 FastAPI 创建新任务。

## API / Mock 模式

后端 provider 可通过两种方式配置：

1. 工作台右上角“配置密钥”：保存为本机运行时模型配置，优先级最高。
2. 根目录 `.env`：作为 fallback，适合开发和 CI 环境。

```bash
cp .env.example .env
```

mock 模式：

```dotenv
DEFAULT_LLM_PROVIDER=mock
DEFAULT_EMBEDDING_PROVIDER=mock
```

真实模式示例：

```dotenv
DEFAULT_LLM_PROVIDER=qwen
DEFAULT_EMBEDDING_PROVIDER=jina
QWEN_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
QWEN_API_KEY=你的_Qwen_API_Key
JINA_API_KEY=你的_Jina_API_Key
```

运行时配置保存位置：

- macOS / Linux：`~/.docforge/model_config.json`
- Windows：`%APPDATA%/DocForge/model_config.json`

v0.1 本地单机版允许该文件明文保存 API Key，只用于本机试用，不是生产级密钥托管方案。后续生产化应接入系统 Keychain、KMS 或用户级加密存储。不要把真实 API Key、运行时配置文件或 `.env` 提交到 git。

前端配置位于 `frontend/docforge-web/.env`：

```bash
cd frontend/docforge-web
cp .env.example .env
```

```dotenv
VITE_DOCFORGE_API_BASE_URL=http://127.0.0.1:8000/api
VITE_DOCFORGE_USE_MOCK=false
```

- `VITE_DOCFORGE_USE_MOCK=false`：调用真实 FastAPI，上传真实资料、执行真实 action、下载真实 DOCX。

## v0.1 主流程启动

Vue 工作台是 v0.1 正式入口。配置并测试模型密钥后，上传自有产品文档，Agent 区会提示用户回复“开始”；进入后续阶段后可回复“继续”。“开始 / 开始写作 / 开始生成 / 继续”是受限结构化指令，前端会调用：

```text
POST /api/runs/{run_id}/actions/start
```

该指令不会作为产品事实证据。底层仍经过 workflow 状态校验和 action guard；底部主操作按钮仅作为备用入口。

FastAPI 与 Streamlit 入口复用统一 workflow 服务装配，不再各自维护一套 `WorkflowServiceRegistry`。正式 FastAPI 入口会注入资料解析、Evidence 抽取、产品理解、人工确认、写作、审计和 DOCX 导出服务。

资料边界保持不变：外部参考资料只用于目录、章法、配图方式和语言风格；产品截图仅作为配图候选和展示材料，不做 OCR，也不能作为产品事实证据。
- `VITE_DOCFORGE_USE_MOCK=true`：使用前端内置 mock 数据，只用于检查界面，不代表真实生成结果。

## 技术栈

开发工具：

- Cursor / Codex / VSCode

运行环境：

- macOS
- Python 3.11 或 3.12
- Node.js
- npm
- Corepack
- pnpm

核心后端：

- Python
- FastAPI
- LangGraph
- Pydantic
- python-docx
- Qdrant Local Persistent Mode

正式前端：

- Vue 3
- Vite
- TypeScript
- Element Plus
- Pinia
- Vue Router
- Axios
- pnpm

模型层：

- QwenProvider
- DeepSeekProvider
- MockProvider

Embedding：

- Jina Embedding
- MockEmbeddingProvider

数据存储：

- `data/runs/{run_id}/state.json`
- `data/runs/{run_id}/sources/`
- `data/runs/{run_id}/exports/`
- `data/qdrant/`

## 证据边界

外部参考软著资料：

- `corpus_type = reference_style`
- `allowed_usage = style_only`
- 只能用于目录结构、章节写法、语言风格、配图方式和软著常见表达。
- 不能用于产品事实、产品功能、技术架构事实、对方产品名称或对方业务描述。

自有产品资料：

- `corpus_type = product_evidence`
- `allowed_usage = factual_evidence`
- 可作为产品事实来源，包括产品介绍、PRD、HLD、详细设计、用户确认信息和其他自有产品文档。

产品截图：

- `corpus_type = product_evidence`
- `allowed_usage = display_material_only`
- `evidence_strength = not_allowed_as_fact`
- 当前 v0.1 仅作为展示材料登记和配图候选。
- 不做 OCR，不做视觉模型解析，不作为强产品事实证据，不用于推断当前版本已实现功能，不进入 WriterAgent 的事实引用链。

## Agent / Workflow 口径

当前团队口径为 **AT-02：软著生成 Agent 团队 v2.1**，包含 14 个核心 Agent / Gate / Service 角色：

1. OrchestratorAgent
2. IntakeAgent
3. MaterialIngestionAgent
4. ProductSourceAgent
5. ReferenceStyleAgent
6. ProductUnderstandingAgent
7. EvidenceExtractorAgent
8. SoftwareDiagnosisAgent
9. TemplateStrategyAgent
10. HumanConfirmGate
11. OutlineAgent
12. WriterAgent
13. AuditAgent
14. ExportAgent

截图相关职责已收敛为资料登记、配图占位和补图建议：`FigureSlotPlannerService` 是非 Agent 的配图占位 / 补图建议服务，不做 OCR、不做真实截图绑定、不做截图事实推断。

WF-02：软著文档生成工作流 v2.1：

```text
OrchestratorAgent 启动任务
  ↓
1. IntakeAgent：创建软著项目
  ↓
2. MaterialIngestionAgent：资料接入与分类
  ↓
3. ProductSourceAgent：产品资料读取与截图素材登记
  ↓
4. ReferenceStyleAgent：参考软著风格分析
  ↓
5. ProductUnderstandingAgent：自有产品理解
  ↓
6. EvidenceExtractorAgent：证据抽取与证据地图构建
  ↓
7. SoftwareDiagnosisAgent：软件类型诊断
  ↓
8. TemplateStrategyAgent：模板推荐与目录策略生成
  ↓
9. HumanConfirmGate：用户确认推荐方案
  ↓
10. OrchestratorAgent：生成并冻结 FrozenDocPlan
  ↓
11. OutlineAgent：基于 FrozenDocPlan 生成详细目录
  ↓
12. PlanQualityGate：生成前质量门禁
  ↓
13. WriterAgent：写 v1 初稿
  ↓
14. AuditAgent：审查 v1
  ↓
15. DraftQualityGate：判断是否通过
      ├─ 通过：进入 ExportAgent
      └─ 不通过：WriterAgent 根据审计意见写 v2 / v3
  ↓
16. ExportAgent：导出 DOCX
```

## 用户产物

最终用户通过 Vue 工作台下载 DOCX。本地文件位于：

```text
data/runs/{run_id}/exports/
```

正常版：

```text
软件著作权文档.docx
```

风险版：

```text
软件著作权文档_风险版.docx
```

内部产物不作为正式下载物：

- `state.json`
- `evidence_map.json`
- `audit_report_v*.json`
- `quality_gate_report_v*.json`
- `revision_trace_v*.json`
- `export_manifest.json`

## 当前 v0.1 未完成能力

- 不做登录权限。
- 不做多项目管理。
- 不做 SSE。
- 产品类型与文档策略采用条件自动确认；冲突、低置信度、资料不足或证据边界风险时保留人工确认。
- `confirm-product-type` / `confirm-doc-plan` 已接入真实确认与 `FrozenDocPlan` 冻结流程。
- 右侧关键策略写入后端 run settings；冻结后修改需显式重启策略评估并失效下游产物。
- 不导出 PDF。
- 不导出独立审计报告。
- 不做截图 OCR。
- 不做网页 URL 采集。
- 不接代码仓库。
- Streamlit 仍保留为调试入口。

## 运行测试

```bash
scripts/test_quick.sh
```

普通开发默认先按 [docs/test_impact_matrix.md](docs/test_impact_matrix.md) 选择受影响测试；需要基础后端基线时使用 `scripts/test_quick.sh`。完整回归使用 `scripts/test_full.sh`。更多测试分层和命令说明见 [docs/testing.md](docs/testing.md)。

开发检查：

```bash
.venv/bin/ruff check .
.venv/bin/mypy docforge_core tests
git diff --check
```

更多说明见：

- [docs/CURRENT_STATUS.md](docs/CURRENT_STATUS.md)
- [docs/ARCHITECTURE_DECISIONS.md](docs/ARCHITECTURE_DECISIONS.md)
- [docs/SPRINT_ROADMAP.md](docs/SPRINT_ROADMAP.md)
- [docs/LLM_HANDOFF.md](docs/LLM_HANDOFF.md)
- [frontend/docforge-web/README.md](frontend/docforge-web/README.md)
