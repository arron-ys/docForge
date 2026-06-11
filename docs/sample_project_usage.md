# 样例工程使用说明

样例工程位于 `tests/fixtures/e2e_sample/`，用于本地演示和回归测试。

## 包含资料

- `reference_soft_copyright.md`：参考软著写法资料，只能作为 `reference_style / style_only`。
- `product_prd.md`
- `product_hld.md`
- `product_intro.md`
- `screenshots/login_page.png`
- `screenshots/dashboard_page.png`

导入后共 6 个 source：

- reference：1
- product：3
- screenshot：2

## v0.1 推荐使用方式

v0.1 正式产品入口是 Vue3 三栏式 Agent 工作台。

样例工程可以先通过 Streamlit 调试入口创建或导入任务，获得 `run_id` 后再回到 Vue 工作台体验。

推荐步骤：

1. 启动 FastAPI：`.venv/bin/python -m uvicorn api.main:app --reload`。
2. 启动 Vue 前端：`cd frontend/docforge-web && pnpm dev`。
3. 可选启动 Streamlit 调试入口：`streamlit run app/main.py`。
4. 在 Streamlit 调试入口中创建新任务。
5. 展开“样例工程”，点击“加载本地样例工程”。
6. 获得 `run_id`。
7. 打开 Vue 工作台：`http://127.0.0.1:5173/?run_id=<run_id>`。
8. 在 Vue 工作台查看资料上下文、Agent 消息、右侧诊断和导出结果。

Streamlit 是调试入口，不是 v0.1 正式产品入口。

## 样例导入幂等性

重复点击加载不会重复导入。只有当 6 个 `metadata.fixture_path` 完整存在时才会跳过。

样例导入器会 fail closed，不自动修复：

- 只有部分样例 source 已存在。
- `metadata.fixture_path` 缺失、为空或不是字符串。
- 出现未知 `fixture_path`。
- 出现重复 `fixture_path`。

原因：当前 `SourceFileRegistry` 会生成新的 source_id 和唯一落盘文件名，自动补齐可能污染状态。

遇到异常时，Streamlit 调试入口会显示用户友好错误；开发细节在默认折叠的“开发调试信息”中。

## 截图边界

样例截图只表示“用户上传过截图文件”和“可用于展示材料登记 / 配图候选”。当前 v0.1：

- 不读取图片内容。
- 不做 OCR。
- 不做视觉模型解析。
- 不自动绑定真实截图。
- 不把截图作为产品事实证据。
- 不用截图推断当前版本已实现功能。

截图 evidence 不得进入 Writer evidence bundle、SectionPlan required evidence、draft citations 或 FrozenDocPlan 的 allowed product evidence。
