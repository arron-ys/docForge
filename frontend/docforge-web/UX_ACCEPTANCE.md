# DocForge Web UX 验收清单

本清单用于 DocForge v0.1 Vue 正式入口的开发验收，不是正式用户文档。

## API 模式

1. 无 `run_id`
   - 打开 `/`。
   - 应显示产品化空状态，说明需要 `/?run_id=20260609_143000_ab12`。
   - 不应调用无效 API，不应看起来像崩溃。

2. `run_id` 不存在或非法
   - 打开 `/?run_id=bad-run-id`。
   - 应展示用户可读错误和恢复建议。
   - 不应展示 Python trace、内部路径或 Axios 原始对象。

3. 带合法 `run_id`
   - FastAPI 启动后打开 `/?run_id=<真实任务编号>`。
   - 顶部应展示项目名、当前阶段、健康状态、下一步。
   - 不应展示 `workflow_status`、`next_action`、`qdrant_collection`、`state.json`。

4. 上传 reference
   - 上传弹窗选择“外部参考资料”。
   - 说明应强调只用于目录、章法、配图方式和语言风格，不作为产品事实来源。
   - 成功后左侧出现 reference_style / style_only 边界文案。

5. 上传 product
   - 上传弹窗选择“自有产品资料”。
   - 说明应强调可作为产品事实来源。
   - 成功后左侧出现 product_evidence / factual_evidence 边界文案。

6. 上传 screenshot
   - 上传弹窗选择“产品截图”。
   - 说明应强调 display_material_only、仅作为配图候选和展示材料登记、v0.1 不做 OCR、不作为强产品事实证据、不用于推断当前版本已实现功能。
   - 成功后左侧产品截图区展示相同边界。

7. 当前主操作
   - 点击当前主操作。
   - 执行中按钮应禁用或 loading。
   - 成功后应刷新 workspace。
   - 失败后保留当前页面并展示业务错误。

8. 非法 action / 预留确认动作
   - 触发当前状态不允许的 action。
   - 409 应展示“当前状态还不能执行该操作，请先完成上一阶段。”
   - `confirm-product-type` / `confirm-doc-plan` 预留时，应说明完整确认流程将在后续版本接入。

9. artifact 不存在
   - 左侧不可下载产物按钮应禁用。
   - 应说明“文档尚未生成，完成正文生成和风险检查后才可下载。”

10. artifact 可下载
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
