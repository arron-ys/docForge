# LLM Handoff

本文档给新接手 DocForge 的 LLM / 开发者使用。先读本文件，再读 `CURRENT_STATUS.md`、`ARCHITECTURE_DECISIONS.md` 和代码。

## 接手时先确认

1. 先运行或读取当前测试结果，不要相信旧 README。
2. 先看 `frontend/docforge-web/README.md`，确认 Vue 工作台是 v0.1 正式入口。
3. 再看 `api/main.py`，确认 FastAPI API 层。
4. 再看 `docforge_core/domain/enums.py` 和 `docforge_core/domain/schemas.py`。
5. 再看 `docforge_core/workflow/orchestrator.py`。
6. 再看 `docforge_core/workflow/diagnostics.py` 和 `docforge_core/workflow/user_facing_errors.py`。
7. 再看 `docforge_core/exporters/docx_acceptance.py`。
8. 最后看 `app/main.py`，它是 Streamlit 开发调试入口 / 旧 Demo 入口。

如果文档与代码冲突，以代码和测试为准。

## 当前 v0.1 架构

当前版本为 **墨衡 DocForge v0.1**。正式产品入口是 Vue3 三栏式 Agent 工作台，FastAPI 作为 API 层，`docforge_core` 作为核心业务模块。

Streamlit 只作为开发调试入口。

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
- FastAPI 负责 WorkspaceView API、Source Upload API、Run Action API、Diagnostics API、Artifact Download API、用户可读状态映射和 action 状态校验。
- `docforge_core` 负责 workflow 状态机、Agent / Service、Evidence、FrozenDocPlan、QualityGate、DOCX 导出、Qdrant 检索和状态持久化。
- Streamlit 负责开发调试和旧 Demo 验证。

`WorkflowOrchestratorService` 是薄编排层，只调度已有 service / agent，并做 guard、rollback 和 stale artifact 检查。不要把业务生成逻辑塞进 Orchestrator。

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

截图相关职责已收敛到资料登记、质量门禁补图建议和导出占位处理。`FigureSlotPlannerService` 是非 Agent 的配图占位 / 补图建议服务，不做 OCR、不做真实截图绑定、不做截图事实推断。

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

## 不要恢复的旧路线

禁止恢复：

- 关键词匹配主导产品能力判断。
- 根据单个词命中推断模块、平台能力或完整流程。
- 使用 reference style 作为产品事实。
- 独立截图绑定 Agent。
- MVP OCR。
- MVP 视觉模型解析。
- MVP 真实图片插入 DOCX。
- 将截图作为产品事实证据。
- 通过 Streamlit 暴露内部 artifact。

这些路线已经被架构纠偏废弃。

## Evidence-grounded reasoning 要点

LLM 可以做语义理解，但系统必须约束证据：

- 当前产品事实只能来自 `product_evidence / factual_evidence`。
- 每个能力必须有 evidence id 和 quote。
- quote 必须真实存在。
- quote 必须语义支持 claim。
- validated current capability 才能进入当前 ProductProfile。
- planned / unknown / unsupported 只能进入风险或不确定信息，不能写成当前功能。
- 冻结计划前后都要校验 trace 和 hash。

不要让 LLM “根据常识补全”产品能力。

## reference_style 使用边界

可以使用：

- 写法。
- 章节组织。
- 目录结构。
- 配图方式。

不能使用：

- 产品功能。
- 产品事实。
- 当前能力。
- 业务对象、用户角色、页面或流程事实。

## 截图证据边界

产品截图在 v0.1 的统一口径：

- `corpus_type = product_evidence`
- `allowed_usage = display_material_only`
- `evidence_strength = not_allowed_as_fact`
- 仅作为展示材料登记和配图候选。
- 不做 OCR。
- 不做视觉模型解析。
- 不作为强产品事实证据。
- 不用于推断当前版本已实现功能。
- 不进入 WriterAgent 的事实引用链。

## 审计模式

做代码 review 或继续开发时优先看风险：

- evidence 隔离是否被破坏。
- reference style 是否被用作事实。
- planned / unknown 是否被写成 current。
- FrozenDocPlan 是否被绕过。
- SectionPlan 和 draft 是否不一致。
- audit / gate / export lineage 是否断裂。
- Orchestrator 是否误写业务 artifact。
- FastAPI 是否允许前端绕过 workflow。
- Vue 是否泄露内部状态字段或内部 artifact。

## 后续建议方向

优先做：

- Vue 创建任务入口。
- `confirm-product-type` / `confirm-doc-plan` 已接入真实确认与条件自动确认；后续继续完善人工修改目录表单。
- 产品级验收测试矩阵。
- Diagnostics 发现问题后的 fail closed 引导。
- DOCX acceptance 覆盖。
- 内部 artifact 不可下载的回归检查。

不要做：

- 独立截图绑定 Agent。
- OCR。
- 视觉模型解析。
- 在线编辑器。
- 新增大规模业务状态机。

## 协作注意

- 仓库可能有大量未提交的历史变更，不要随意回退。
- 只改与当前任务相关的文件。
- 如果任务是文档同步，严格只改 README 和 docs。
- Python 逻辑、schema、测试和 pyproject 不应在文档同步任务中变动。
- 完成后至少运行 `git diff --check`。
