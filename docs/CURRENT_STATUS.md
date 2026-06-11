# 当前状态

本文档记录 DocForge v0.1 的当前项目口径，供新接手的开发者或 LLM 判断项目进度。若本文档与代码冲突，以 `api/`、`frontend/docforge-web/`、`docforge_core/`、`app/main.py` 和 `tests/` 为准。

## 当前阶段

当前版本为 **墨衡 DocForge v0.1**。

- Vue3 三栏式 Agent 工作台已经完成，并作为 v0.1 正式产品入口。
- FastAPI API 适配层已经完成。
- Vue 工作台已经接入真实 FastAPI，同时保留 mock 模式。
- 用户上传自有产品资料后，可在 Agent 对话区回复“开始”启动主流程；进入后续阶段后可回复“继续”。这些文本只作为结构化 action 指令，不进入产品事实证据链。
- FastAPI 与 Streamlit 入口复用统一 workflow 服务装配，FastAPI 正式入口不再创建空 orchestrator。
- Sprint 4 UX 验收已经通过。
- Streamlit 入口仍然保留，但定位为开发调试入口 / 旧 Demo 入口。
- 最终用户产物为普通版 DOCX 或风险版 DOCX。

## 当前入口

正式产品入口：

```text
frontend/docforge-web
```

API 入口：

```text
api/main.py
```

开发调试入口：

```text
app/main.py
```

启动 FastAPI：

```bash
.venv/bin/python -m uvicorn api.main:app --reload
```

启动 Vue 前端：

```bash
cd frontend/docforge-web
pnpm install
pnpm dev
```

可选启动 Streamlit 调试入口：

```bash
streamlit run app/main.py
```

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

- Vue 工作台负责资料上下文展示、Agent 对话区、右侧运行设置、上传资料、触发结构化 action、展示诊断状态、下载 DOCX、展示错误和下一步建议。
- FastAPI 负责 WorkspaceView API、Source Upload API、Run Action API、Diagnostics API、Artifact Download API、用户可读状态映射、action 状态校验，并防止前端绕过 workflow。
- `docforge_core` 负责 workflow 状态机、Agent / Service、Evidence、FrozenDocPlan、QualityGate、DOCX 导出、Qdrant 检索和状态持久化。
- Streamlit 只负责开发调试和旧 Demo 验证。

当前主流程启动口径：

- 上传自有产品文档后，WorkspaceView 会返回“回复开始”的 Agent 引导；主流程已启动后，前端会引导回复“继续”。
- 前端识别“开始 / 开始写作 / 开始生成 / 继续”，调用 `POST /api/runs/{run_id}/actions/start`。
- `/actions/start` 会检查自有产品文档、模型配置和当前状态，然后通过 workflow orchestrator 推进到用户确认点、可解释错误或终态。
- 外部参考资料和产品截图不能作为启动主流程的产品事实依据。

## 事实来源

优先读取：

- `api/main.py`
- `frontend/docforge-web/README.md`
- `docforge_core/domain/enums.py`
- `docforge_core/domain/schemas.py`
- `docforge_core/io/state_store.py`
- `docforge_core/agents/`
- `docforge_core/gates/`
- `docforge_core/exporters/`
- `docforge_core/workflow/`
- `app/main.py`
- `tests/unit/`

README 和 docs 是说明材料，不是状态机事实源。

## Agent 团队口径

当前统一为 **AT-02：软著生成 Agent 团队 v2.1**，包含 14 个核心 Agent / Gate / Service 角色：

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

截图相关职责已收敛：

- `MaterialIngestionAgent` 登记截图。
- `ProductSourceAgent` 登记截图作为展示素材。
- `PlanQualityGate` 判断是否需要用户补充截图或文字替代说明。
- `ExportAgent` 按结构化章节内容和截图策略处理可用图片或占位说明。

`FigureSlotPlannerService` 是非 Agent 的配图占位 / 补图建议服务，不做 OCR、不做真实截图绑定、不做截图事实推断。

## Workflow 口径

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

## 证据边界

外部参考软著资料：

- `corpus_type = reference_style`
- `allowed_usage = style_only`
- 只能用于目录结构、章节写法、语言风格、配图方式和软著常见表达。
- 不能用于产品事实、产品功能、技术架构事实、对方产品名称或对方业务描述。

自有产品资料：

- `corpus_type = product_evidence`
- `allowed_usage = factual_evidence`
- 可以作为产品事实来源。

产品截图：

- `corpus_type = product_evidence`
- `allowed_usage = display_material_only`
- `evidence_strength = not_allowed_as_fact`
- 仅作为展示材料登记和配图候选。
- 不做 OCR，不做视觉模型解析，不作为强产品事实证据，不用于推断当前版本已实现功能，不进入 WriterAgent 的事实引用链。

## 已完成的主要能力

- Vue3 三栏式 Agent 工作台。
- FastAPI API 适配层。
- WorkspaceView、资料上传、Run Action、Diagnostics 和 Artifact Download API。
- 资料上传、注册和 run-scoped 文件目录。
- 解析 `.docx`、`.pdf`、`.md`、`.txt`、`.html` 和截图登记。
- Evidence 抽取、Qdrant 存储和 payload filter 检索。
- LLM / Embedding provider 抽象与 mock 测试路径。
- reference style 分析，且只允许用于写法。
- 产品能力、产品事实和产品画像的 evidence-grounded 构造。
- source grounding、semantic grounding 和 validation trace。
- 软件类型诊断与模板推荐。
- 人工确认、模板决策和 `FrozenDocPlan` 冻结。
- Outline、SectionPlan、PlanQualityGate。
- WriterAgent v1 初稿生成。
- 配图占位与补图清单。
- AuditAgent 确定性审计和 LLM claim-support 审计。
- DraftQualityGate、v2/v3 受控修订和风险版分支。
- DOCX ExportAgent 普通版 / 风险版导出。
- WorkflowOrchestratorService 主流程编排。
- WorkflowDiagnosticsService 只读健康诊断。
- UserFacingErrorMapper 用户友好错误映射。
- DocxAcceptanceChecker 交付 DOCX 验收。

## 当前未完成能力

- 不做登录权限。
- 不做多项目管理。
- 不做 SSE。
- `confirm-product-type` / `confirm-doc-plan` 已接入真实确认、确认审计记录与 `FrozenDocPlan` 冻结。
- 默认无冲突场景支持条件自动确认；风险、冲突、证据不足和策略中途变更仍进入人工确认或重启评估。
- 不导出 PDF。
- 不导出独立审计报告。
- 不做截图 OCR。
- 不做网页 URL 采集。
- 不接代码仓库。
- Streamlit 仍保留为调试入口。

## 重要 artifact

面向内部追溯：

- `state.json`
- `evidence/evidence_map.json`
- `drafts/draft_v1.json`
- `drafts/figure_slots_v1.json`
- `drafts/audit_report_v*.json`
- `drafts/quality_gate_report_v*.json`
- `drafts/revision_trace_v*.json`
- `exports/export_manifest.json`

面向用户：

- `exports/软件著作权文档.docx`
- `exports/软件著作权文档_风险版.docx`

用户最终通过 Vue 工作台下载 DOCX，内部 artifact 不作为正式下载物。

## 已废弃路线

- 用关键词匹配判断产品能力。
- 根据单个词命中推断完整模块或平台能力。
- 将 reference style 作为产品事实。
- 独立截图绑定 Agent。
- 截图 OCR 或视觉模型解析。
- 将截图作为产品事实证据。
- DOCX 自动插入真实截图作为 v0.1 必备能力。

这些路线会造成产品能力污染、证据污染或 v0.1 范围失控。
