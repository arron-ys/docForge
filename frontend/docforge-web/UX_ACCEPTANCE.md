# DocForge Web UX 验收清单

本清单用于 DocForge v0.1 Vue 正式入口的开发验收，不是正式用户文档。

## API 模式

1. 无 `run_id`
   - 打开 `/`。
   - 应通过 FastAPI 自动加载最近更新的本地任务，并把地址栏同步为 `/?run_id=<真实任务编号>`。
   - 如果本地没有任何任务，应通过 FastAPI 自动创建新任务并进入三栏工作台。
   - 不应停留在要求用户手动填写 `run_id` 的死胡同页面。

2. `run_id` 不存在或非法
   - 打开 `/?run_id=bad-run-id`。
   - 应展示用户可读错误和恢复建议。
   - 不应展示 Python trace、内部路径或 Axios 原始对象。

3. 带合法 `run_id`
   - FastAPI 启动后打开 `/?run_id=<真实任务编号>`。
   - 顶部应展示项目名、当前阶段、健康状态、下一步。
   - 不应展示 `workflow_status`、`next_action`、`qdrant_collection`、`state.json`。
   - 顶部最右侧应展示“配置密钥”，不再展示导出入口主按钮。

4. 左侧资料区
   - 左侧不应再展示“当前运行任务”重复区块。
   - 左侧只保留“外部参考资料 / 自有产品资料 / 生成产物 / 导出历史”三个一级区块。
   - 不应再展示独立“产品截图”一级区块。
   - 外部参考资料为空时，应展示可点击虚线上传卡片；已有资料时，应以紧凑列表展示多个文件。
   - 自有产品资料为空时，应展示可点击虚线上传卡片；已有资料时，应按“产品文档 / 产品截图”二级分组展示。

5. 上传 reference
   - 上传弹窗选择或默认选中“外部参考资料”。
   - 说明应强调只用于目录、章法、配图方式和语言风格，不作为产品事实来源。
   - 成功后左侧应展示“仅参考目录、章法、配图方式和语言风格”和“不能作为产品事实来源”。

6. 上传 product
   - 上传弹窗选择或默认选中“自有产品资料”。
   - 上传弹窗只展示“外部参考资料 / 自有产品资料”两个一级类型。
   - 自有产品资料说明应强调：文档可作为产品事实依据；图片仅作为配图候选和展示，不做 OCR，不作为产品事实证据。
   - 上传图片后，前端应在自有产品资料内部的“产品截图”二级分组展示。
   - 上传按钮文案应为“上传”。

8. 解析状态
   - `saved` / `pending` 状态应映射为“待解析”，hover 后说明真实解析仍以后端服务配置为准。
   - `parsing` / `embedding` 状态应映射为“解析中”，文件名区域显示浅色进度感；没有真实 progress 时不显示假百分比。
   - `parsed` 状态应展示“已解析”。
   - `failed` 状态应展示“解析失败”。
   - `skipped` 状态应展示“已跳过”。

9. 模型密钥配置
   - 点击右上角“配置密钥”应打开“配置模型密钥”弹窗。
   - 弹窗默认只展示 Qwen API Key 和 Jina API Key 两个核心输入框。
   - LLM 区块应展示“大模型 LLM”、Qwen、校验状态和“测试 LLM 连接”按钮。
   - Embedding 区块应展示“向量模型 Embedding”、Jina、校验状态和“测试 Embedding 连接”按钮。
   - 模型名称和 BaseURL 默认收进“高级设置”，默认不直接展示。
   - LLM 模型服务商只展示 Qwen；Embedding 模型服务商只展示 Jina。
   - Qwen BaseURL 默认是 `https://dashscope.aliyuncs.com/compatible-mode/v1`。
   - Jina BaseURL 默认是 `https://api.jina.ai/v1`。
   - 当前本地单机测试版 API Key 输入框为明文文本框，便于核对测试 Key。
   - 打开弹窗时应调用 `GET /api/model-config`，回填 provider / model / baseURL。
   - 已保存密钥仍使用 masked key 文案展示；输入框中的当前测试 Key 可明文核对。
   - 点击“测试 LLM 连接”应调用 `POST /api/model-config/test-llm`。
   - 点击“测试 Embedding 连接”应调用 `POST /api/model-config/test-embedding`。
   - 点击“测试全部”应依次触发 LLM 和 Embedding 的测试逻辑。
   - 测试成功显示“校验通过”；测试失败显示后端返回的人话错误。
   - 不论是否校验通过，都允许点击“保存配置”。
   - 保存应调用 `POST /api/model-config`，刷新页面后再次打开弹窗仍能看到 provider / model / baseURL 和 masked key。
   - 保存后后端 provider 优先使用运行时配置；没有运行时配置时 fallback 到根目录 `.env`。
   - 不应把完整 API Key 从后端返回给前端、打印到 console、写入 mock 数据或提交到 git。

10. 中间和右侧文案
   - 中间标题应为“Agent 工作区”，不应展示 workflow-driven。
   - 自由文本输入应说明“本地备注，暂不参与生成”。
   - 右侧说明不应展示 prior_hint、ActionGuard、FastAPI Action API 等主 UI 文案。
   - 右侧栏顶部不应展示“模型密钥状态”大卡片。
   - 外部参考资料始终明确不能作为产品事实来源。
   - 产品截图始终明确不做 OCR、不作为产品事实证据。

11. 当前主操作
   - 点击当前主操作。
   - 执行中按钮应禁用或 loading。
   - 成功后应刷新 workspace。
   - 失败后保留当前页面并展示业务错误。

12. 非法 action / 预留确认动作
   - 触发当前状态不允许的 action。
   - 409 应展示“当前状态还不能执行该操作，请先完成上一阶段。”
   - `confirm-product-type` / `confirm-doc-plan` 预留时，应说明完整确认流程将在后续版本接入。

13. artifact 不存在
   - 左侧不可下载产物按钮应禁用。
   - 应说明“文档尚未生成，完成正文生成和风险检查后才可下载。”

14. artifact 可下载
    - 可下载时走 `/api/artifacts/{artifact_id}/download`。
    - 下载中应显示 loading。
    - 成功后提示“已开始下载：xxx.docx。”

## Mock 模式

1. 设置 `VITE_DOCFORGE_USE_MOCK=true`。
2. 前端应使用内置 mock 数据，不调用真实 API。
3. 三栏布局、上传入口、action 卡片和截图边界文案仍可正常展示。
4. mock 模式不代表真实生成结果。

## 布局回归

1. 页面保持 100vh。
2. body 不出现页面级长滚动。
3. 左侧、中间、右侧各自内部滚动。
4. 输入框固定在中间面板底部。
5. 宽度低于 1180px 时显示清楚的宽度建议。
