# 架构决策记录

本文档记录 DocForge v0.1 的关键架构决策。后续开发不得用旧文档或旧假设反向修改当前代码。

## ADR-001: v0.1 正式入口是 Vue 工作台

DocForge v0.1 的正式产品入口是 `frontend/docforge-web` 下的 Vue3 三栏式 Agent 工作台。

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

Streamlit 入口 `app/main.py` 仍保留，但只作为开发调试入口 / 旧 Demo 入口。

该决策避免继续沿用旧版单入口说明。v0.1 本地试用需要同时启动 FastAPI 和 Vue 前端；Qdrant 使用 Local Persistent Mode，不需要独立 Qdrant Server。

## ADR-002: FastAPI 是正式 API 层

FastAPI 入口为 `api/main.py`。

FastAPI 负责：

- WorkspaceView API。
- Source Upload API。
- Run Action API。
- Diagnostics API。
- Artifact Download API。
- 用户可读状态映射。
- action 状态校验。
- 防止前端绕过 workflow。

前端只触发结构化 action，不直接修改 workflow 状态。

## ADR-003: reference_style 不能作为产品事实

`reference_style` 只允许用于：

- 目录结构参考。
- 章节组织方式参考。
- 配图方式参考。
- 语言风格参考。
- 软著常见表达参考。

`reference_style` 不允许用于：

- 推断当前产品功能。
- 补充当前产品事实。
- 支撑 WriterAgent 生成产品能力描述。
- 作为 AuditAgent 接受的事实证据。
- 使用对方产品名称或对方业务描述。

原因：参考软著来自外部产品，若作为事实来源会污染当前产品能力和软著正文。

## ADR-004: 废弃关键词主导能力判断

废弃路线：

```text
EvidenceItem
  -> 关键词规则 + LLM 输出合并
  -> ProductProfile
  -> 关键词规则诊断
  -> DiagnosisResult
  -> TemplateStrategy
```

该路线的问题是关键词命中不等于产品能力成立。例如资料中出现“支持仿真数据导入”，真正能力可能是数据导入，不是仿真平台能力。用关键词命中会造成产品能力污染。

保留关键词只能作为低风险辅助提示或测试构造，不得作为产品能力真值来源。

## ADR-005: 采用 Evidence-grounded LLM reasoning

当前正确路线：

```text
EvidenceItem
  -> EvidencePacket 构造
  -> LLM 候选能力 / 事实抽取
  -> source grounding: 校验 evidence_id / source_id / quote 真实存在
  -> semantic grounding: LLM verifier 判断 quote 是否语义支持 claim
  -> ProductCapability + CapabilityValidationTrace
  -> ProductFact / ProductProfile
  -> SoftwareDiagnosisAgent 基于 validated current capability 诊断
  -> TemplateStrategyAgent 跟随 DiagnosisResult 推荐模板
```

产品能力进入当前版本必须满足：

- 来源是 `product_evidence`。
- `allowed_usage = factual_evidence`。
- 有 `evidence_id`。
- 有 `quote`。
- `quote` 在对应 EvidenceItem 中真实存在。
- `quote` 语义支持 claim。
- `implementation_status` 明确为 `current`、`planned` 或 `unknown`。
- `validation_status` 明确。
- `ProductCapability` 有 `CapabilityValidationTrace`。
- `FrozenDocPlan` 冻结时重新校验 trace 和 hash。

系统职责是约束和审计，不是让 LLM 自由发挥。

## ADR-006: 产品截图仅是展示材料

产品截图在 v0.1 的统一口径：

- `corpus_type = product_evidence`
- `allowed_usage = display_material_only`
- `evidence_strength = not_allowed_as_fact`

产品截图只能作为展示材料登记和配图候选，不能作为产品事实来源。

截图相关限制：

- 不做 OCR。
- 不做视觉模型解析。
- 不作为强产品事实证据。
- 不用于推断当前版本已实现功能。
- 不抽取页面按钮、菜单、功能入口并作为事实。
- 不进入 WriterAgent 的事实引用链。

## ADR-007: FrozenDocPlan 是生成合同

`FrozenDocPlan` 是人工确认后的生成合同。后续节点必须遵守：

- OutlineAgent 不得擅自改变一级章节。
- WriterAgent 只能使用 SectionPlan 要求的 product evidence。
- AuditAgent 必须以 FrozenDocPlan、SectionPlan 和 evidence lineage 为审计依据。
- planned / unknown / unsupported 功能不得作为当前版本能力写入。
- 冻结后的 claim/support hash 不允许被绕过。

## ADR-008: WriterAgent 是受控写作执行器

WriterAgent 不根据标题自由补全正文，也不使用 reference style 或产品截图作为产品事实。

WriterAgent 的输入边界：

- `FrozenDocPlan`
- `DocumentOutline`
- `SectionPlan`
- `required_evidence_ids`
- `required_capability_ids`
- `required_fact_ids`
- 写作安全约束

WriterAgent 输出 `drafts/draft_v1.json`，不输出 DOCX，不绑定截图，不生成内部审计结论。

## ADR-009: 配图占位是非 Agent 辅助服务

v0.1 不设置独立截图绑定 Agent。截图相关职责收敛为：

- `MaterialIngestionAgent` 登记截图。
- `ProductSourceAgent` 登记截图作为展示素材。
- `PlanQualityGate` 判断是否需要用户补充截图或文字替代说明。
- `ExportAgent` 按结构化章节内容和截图策略处理可用图片或占位说明。

`FigureSlotPlannerService` 是非 Agent 的配图占位 / 补图建议服务：

- 基于 `draft_v1.json`、`SectionPlan`、`FrozenDocPlan` 生成配图占位。
- 输出 `drafts/figure_slots_v1.json`。
- 告诉用户每个章节建议补什么图。
- 输出 `recommended_caption`。
- 输出 `recommended_screenshot`。
- 输出 `user_action`。
- `status` 默认为 `missing`。
- 不绑定真实图片。
- 不读取图片。
- 不 OCR。
- 不调用视觉模型。
- 不做截图事实推断。

## ADR-010: v0.1 DOCX 使用图片占位符

v0.1 DOCX 导出只生成 Word 文档，不要求插入真实截图。缺图章节使用占位符和补图说明，不阻塞导出。

风险版 DOCX 只暴露风险提示和摘要，不能 dump 完整 audit report。

## ADR-011: 内部产物不面向用户下载

以下文件是内部追溯产物：

- `state.json`
- `evidence_map.json`
- `audit_report_v*.json`
- `quality_gate_report_v*.json`
- `revision_trace_v*.json`
- `export_manifest.json`

用户最终只通过 Vue 工作台下载 DOCX。

DOCX 用户可见文本不得泄露：

- `evidence_id`
- `source_id`
- raw quote
- `finding_id`
- source hash
- audit / gate / manifest / state 路径

## ADR-012: Orchestrator 是薄编排层

`WorkflowOrchestratorService` 只负责根据 `next_action` 调度已有 service / agent，并做前置和后置 guard。

它不负责：

- 生成产品事实。
- 生成正文。
- 改写业务 artifact。
- 创建外部 provider。
- 绕过人工确认。
- 绕过质量门禁。

编排失败必须 fail closed，业务状态不得被错误推进。
