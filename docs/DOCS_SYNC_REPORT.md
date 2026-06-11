# 文档同步报告

本报告记录 DocForge v0.1 文档同步收尾结果。

## 一、本次扫描范围

本次扫描了项目内以下文档类型：

- `*.md`
- `*.txt`
- `*.rst`
- `*.docx`
- `*.doc`

扫描时排除了：

- `data/runs/**`
- `data/qdrant/**`
- `node_modules/**`
- `.venv/**`
- `frontend/docforge-web/node_modules/**`

扫描到的项目说明文档：

- `README.md`
- `frontend/docforge-web/README.md`
- `frontend/docforge-web/UX_ACCEPTANCE.md`
- `docs/CURRENT_STATUS.md`
- `docs/LLM_HANDOFF.md`
- `docs/ARCHITECTURE_DECISIONS.md`
- `docs/SPRINT_ROADMAP.md`
- `docs/sample_project_usage.md`
- `docs/local_e2e_acceptance.md`

扫描到但未作为项目说明文档改写的文档：

- `docforge_core/prompts/*.md`：属于 prompt 文件，任务要求禁止修改 Agent / prompt。
- `tests/fixtures/e2e_sample/*.md`：属于样例输入材料和测试 fixture，任务要求不要修改样例输入材料和 tests。
- `.pytest_cache/README.md`：工具缓存文件，不属于项目说明文档。

## 二、本次修改的文档

- `README.md`
- `frontend/docforge-web/README.md`
- `frontend/docforge-web/UX_ACCEPTANCE.md`
- `docs/CURRENT_STATUS.md`
- `docs/LLM_HANDOFF.md`
- `docs/ARCHITECTURE_DECISIONS.md`
- `docs/SPRINT_ROADMAP.md`
- `docs/sample_project_usage.md`
- `docs/local_e2e_acceptance.md`

主要同步内容：

- 当前版本统一为墨衡 DocForge v0.1。
- Vue3 三栏式 Agent 工作台统一为正式产品入口。
- FastAPI 统一为正式 API 层，入口为 `api/main.py`。
- Streamlit 统一为开发调试入口 / 旧 Demo 入口。
- 本地启动方式统一为同时启动 FastAPI 和 Vue 前端。
- 技术栈补齐 Node.js、pnpm、Vue 3、Vite、TypeScript、Element Plus、Pinia、Vue Router、Axios、FastAPI。
- 证据边界统一为 reference style、product evidence、screenshot display material 三类。
- 产品截图统一为 `display_material_only`，不做 OCR，不做视觉模型解析，不作为强产品事实证据。
- Agent 团队统一为 AT-02 软著生成 Agent 团队 v2.1，14 个核心 Agent / Gate / Service 角色。
- Workflow 统一为 WF-02 软著文档生成工作流 v2.1。

## 三、本次新增的文档

- `docs/本地试用操作手册.md`
- `docs/DOCS_SYNC_REPORT.md`

## 四、未修改文档及原因

- `docforge_core/prompts/*.md`：prompt 属于 Agent 行为边界，本次明确不改 Agent 和 prompt。
- `tests/fixtures/e2e_sample/*.md`：测试 fixture 和样例输入材料不属于项目说明文档，本次明确不改 tests 和样例输入材料。
- `.pytest_cache/README.md`：缓存文件，不属于项目说明文档。

## 五、docx / doc 检查结果

本次扫描未发现项目说明类 `.docx` 或 `.doc` 文件。

因此没有需要自动更新但无法安全处理的 Word 文档，也没有需要建议迁移为 Markdown 的 Word 项目说明文档。

## 六、旧口径残留检查

复扫结果：

- 未发现仍把旧调试入口写成正式产品入口的项目说明文档。
- 未发现仍否认 Vue / Node / API 存在的项目说明文档。
- 未发现仍写本地只需启动旧调试入口的项目说明文档。
- 未发现仍把截图描述为事实强支撑的项目说明文档。
- 未发现仍把图片解析能力描述为事实抽取链路的项目说明文档。
- 未发现仍将旧截图绑定名称写成当前独立 Agent 的项目说明文档。
- 未发现仍把当前 Agent 团队写成旧数量口径的项目说明文档。
- 未发现仍把当前阶段写成旧前端 Sprint 的项目说明文档。
- 未发现仍否认后端 API 服务存在的项目说明文档。
- 未发现仍否认 Node.js / npm / pnpm 项目存在的项目说明文档。

## 七、后续人工检查建议

建议后续人工只做轻量复核：

- 确认实际本地环境的 Python / Node / pnpm 安装命令是否需要补充平台差异说明。
- `confirm-product-type` / `confirm-doc-plan` 后端能力、条件自动确认、本地试用手册和前端 README 已同步。
- 如果未来新增 Word 格式项目说明文档，建议迁移为 Markdown，便于版本控制和自动扫描。

## 八、前端工具链补充同步

本次补充记录前端开发环境要求：

- 前端依赖由 Node.js / npm / Corepack / pnpm 管理。
- Python `.venv` 只用于后端 Python 依赖。
- `pnpm` 是 Node.js 包管理器，不属于 Python `.venv`。
- 新增 `scripts/check_frontend_env.sh` 作为根目录环境检查入口。
- 新增 `frontend/docforge-web/scripts/check-env.mjs` 作为前端目录内环境检查入口。
- `frontend/docforge-web/package.json` 已包含 `packageManager`，并补充 `check:env` 脚本。
- `frontend/docforge-web/.gitignore` 已确认包含 `node_modules/`、`dist/`、`.vite/`、`.cache/`、`coverage/`、`*.tsbuildinfo` 和 `*.local`。

脚本只做检查和提示，不会自动执行全局安装、不会修改用户 shell 配置，也不会把 pnpm 安装到 Python `.venv`。
