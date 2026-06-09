# Sprint Roadmap

本文档统一历史 Sprint 路线和当前 v0.1 口径。当前正式产品入口是 Vue3 三栏式 Agent 工作台，不再使用旧版单入口说明。

## 当前 v0.1

- Vue3 三栏式 Agent 工作台已完成并作为正式入口。
- FastAPI API 适配层已完成。
- Vue 工作台已接入真实 FastAPI，同时保留 mock 模式。
- Sprint 4 UX 验收已通过。
- Streamlit 保留为开发调试入口 / 旧 Demo 入口。

当前架构：

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

## 历史 Sprint1: 项目骨架与核心数据结构

- 建立 `docforge_core` 包结构。
- 定义核心 Pydantic schema 和枚举。
- 建立 run-scoped 目录约定。
- 初始化 `DocForgeState`。

## 历史 Sprint2: 上传与 SourceFileRegistry

- 参考软著、自有产品资料、产品截图落盘。
- `SourceItem` 注册和 source id 索引。
- 区分 source_type、file_type、corpus_type 和 allowed_usage。
- Streamlit 当时用于开发验证上传链路，v0.1 正式上传链路已由 Vue 工作台通过 FastAPI 承担。

## 历史 Sprint3: 文档解析与 ParsedAsset

- 文档解析服务。
- 生成 `ParsedAsset`。
- 更新 source parse status 和 parse error。
- 截图作为资产登记，不做 OCR 或视觉识别。

## 历史 Sprint4: LLMProvider / EmbeddingProvider / PromptLoader

- 抽象 LLM provider。
- 接入 Qwen、DeepSeek 和 Mock provider。
- 抽象 embedding provider。
- 接入 Jina 和 Mock embedding provider。
- 建立 prompt loader。

## 历史 Sprint5: Evidence 与 Qdrant

- 从 `ParsedAsset` 生成 `EvidenceItem`。
- 写入 `evidence/evidence_map.json`。
- Qdrant local persistent mode。
- Payload filter 检索。
- 强化 `reference_style` 与 `product_evidence` 隔离。

## 历史 Sprint6: 产品理解、能力抽取、诊断、模板推荐

- `ReferenceStyleAgent`。
- `ProductUnderstandingAgent`。
- `ProductCapability` / `ProductFact`。
- source grounding 与 semantic grounding。
- `CapabilityValidationTrace`。
- `ProductProfileEntityGroundingVerifier`。
- `SoftwareDiagnosisAgent`。
- `TemplateStrategyAgent`。

Sprint6 的关键纠偏：废弃关键词主导能力判断，改为 Evidence-grounded LLM reasoning。

## 历史 Sprint7: HumanConfirmGate 与 FrozenDocPlan

- `HumanConfirmGate`。
- `TemplateConfirmationDecision`。
- `FrozenDocPlanService`。
- `HumanConfirmPipelineService`。
- 人工确认后冻结文档计划。
- 冻结一级章节、能力边界、证据边界和后续 agent 权限。

## 历史 Sprint8: Outline / SectionPlan / PlanQualityGate

- `OutlineAgent`。
- `OutlineValidator`。
- 递归二级/三级章节。
- `SectionPlan` 和 `SectionPlanValidator`。
- `PlanQualityGate`。
- writing goal、section title、section path 和 writing constraints 安全校验。

## 历史 Sprint9: WriterAgent v1 初稿生成

- `WriterAgent`。
- 基于 `FrozenDocPlan`、`DocumentOutline`、`SectionPlan` 和 product evidence 生成 `drafts/draft_v1.json`。
- 写入 `DraftVersion(v1)`。
- 不导出 DOCX。
- 不绑定截图。
- 不使用 reference style 或产品截图作为产品事实。

## 历史 Sprint10: 配图占位与补图清单

- `FigureSlotPlannerService`。
- 生成 `drafts/figure_slots_v1.json`。
- 基于 v1 草稿和 SectionPlan 给出配图占位。
- 输出推荐图注、推荐截图说明和用户补图动作。
- 所有图位状态为 `missing`。
- 该服务不是 Agent，不做 OCR、不做视觉模型解析、不做真实截图绑定、不做截图事实推断。

## 历史 Sprint11: AuditAgent 草稿审计

- `AuditAgentService`。
- 读取 draft 和 figure slots。
- 确定性校验 schema、SectionPlan、evidence、citation、figure slot。
- evidence-grounded LLM claim-support 审计。
- 输出 `drafts/audit_report_v1.json`。
- 不修改 draft 或 figure slots。

## 历史 Sprint12: DraftQualityGate + v2/v3 修订循环

- `DraftQualityGateService`。
- `RevisionLoopService`。
- `DraftRevisionAgent`。
- v1 / v2 / v3 审计与质量门禁循环。
- 质量通过进入普通 DOCX 导出。
- v3 后仍存在风险进入风险版 DOCX 导出。

## 历史 Sprint13: DOCX ExportAgent

- `DocxExportService`。
- 导出普通版 `软件著作权文档.docx`。
- 导出风险版 `软件著作权文档_风险版.docx`。
- 生成内部 `export_manifest.json`。
- 校验 artifact lineage。
- 用户可见文本不得泄露内部 evidence、source、quote、finding 或 manifest 信息。
- 缺图使用占位符，不插入真实截图。

## 历史 Sprint14: WorkflowOrchestratorService + 调试闭环

- `WorkflowOrchestratorService`。
- `WorkflowServiceRegistry`。
- 单步执行、执行到人工确认、提交人工确认、继续到终态。
- 前置 / 后置 guard。
- 状态 rollback。
- stale artifact 拦截。
- 开发调试面板接入。
- DOCX 下载只暴露用户文档。

## 历史 Sprint15: E2E 样例、回归、打包、MVP 收口

- 建立可复现 E2E 样例资料。
- 固化 upload-level E2E 回归路径。
- 加入样例工程导入器和幂等防护。
- 修复截图 evidence 边界，保证截图不能作为正文产品事实。
- 确认内部产物不暴露为用户下载物。
- 确认普通版 / 风险版 DOCX 路径稳定。

## 历史 Sprint16: 产品级验收、诊断和交付可用性

- `WorkflowDiagnosticsService`：只读检查 workflow_status / next_action、一致性、artifact ref、lineage hash、终态 DOCX 可下载性。
- `UserFacingErrorMapper`：将缺资料、等待确认、artifact 缺失、hash mismatch、DOCX 已存在、截图误用等错误映射为用户可理解提示。
- `DocxAcceptanceChecker`：只读检查普通版 / 风险版 DOCX 可打开、包含必要内容、不泄露内部字段。
- 主流程显示健康状态、下一步建议和用户友好错误。
- 开发调试信息默认折叠。
- 样例工程本地验收和 resume / idempotency 测试补强。
- README 和 docs 增加本地验收说明。

## 前端重建 Sprint

- Vue3 三栏式 Agent 工作台完成。
- FastAPI API 适配层完成。
- Vue 工作台接入真实 FastAPI，同时保留 mock 模式。
- Sprint 4 UX 验收通过。
- Vue 工作台成为 DocForge v0.1 正式产品入口。

## 当前未完成能力

- 不做登录权限。
- 不做多项目管理。
- 不做 SSE。
- `confirm-product-type` / `confirm-doc-plan` 完整后端确认流仍待后续。
- 不导出 PDF。
- 不导出独立审计报告。
- 不做截图 OCR。
- 不做网页 URL 采集。
- 不接代码仓库。
- Streamlit 仍保留为调试入口。

## Phase 2 候选方向

- Vue 创建任务入口。
- 完整确认类 action 后端流。
- 用户在线上传 / 拖拽图片到章节。
- 真实图片插入 DOCX。
- 更高级 Word 模板。
- URL 抓取。
- 代码仓库分析。
- 多租户、权限和协作。
