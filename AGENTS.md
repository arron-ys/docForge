# DocForge Agent Instructions

## Python 与测试命令规范

本项目默认 Python 解释器是 `.venv/bin/python`。

- CodeX 不得默认调用裸 `python` 运行测试或开发脚本。
- CodeX 不得长期使用 `python3 -m pytest` 作为默认测试命令；`python3` 只可用于重新创建 `.venv` 这类明确的环境修复动作。
- 所有测试优先通过 `scripts/test_*.sh` 执行；这些脚本会从项目根目录使用 `.venv/bin/python`。
- 如果 `.venv/bin/python` 不存在或不可执行，先报告环境问题，不要静默 fallback 到全局 Python。
- 普通开发不默认跑 full regression，除非满足下方触发条件。
- 最终回复必须说明实际使用的 Python 解释器和测试命令。

## 测试执行协议

普通开发时，CodeX 不得默认运行全量 `pytest`，也不得默认运行 `scripts/test_dev.sh`。

每次改动后按以下顺序选择测试：

1. 先根据 `git diff --name-only` 判断影响范围。
2. 根据 [docs/test_impact_matrix.md](docs/test_impact_matrix.md) 选择最小必要测试。
3. 普通开发默认只运行受影响测试文件；必要时加快速基线：

   ```bash
   scripts/test_quick.sh
   ```

4. 前端代码变更按影响矩阵运行统一前端验证入口：

   ```bash
   scripts/test_frontend.sh
   ```

5. 只有改动涉及后端核心共享逻辑、多个 unit 模块、API 契约或状态模型时，才运行中等范围回归：

   ```bash
   scripts/test_dev.sh
   ```

6. 只有涉及上传、解析、人工确认、状态推进、导出主链路时，才运行 smoke：

   ```bash
   scripts/test_smoke.sh
   ```

7. 只有涉及 workflow 状态机、evidence 边界、DOCX 导出、diagnostics、artifact、公共 fixture 或跨模块协作时，才运行相关 integration 测试；需要全跑 integration 时使用：

   ```bash
   scripts/test_integration.sh
   ```

8. 只有在以下情况才运行 full regression：

   - 用户明确要求。
   - Sprint 完成。
   - Release Candidate 审计。
   - 修改核心架构。
   - 修改全局状态机。
   - 修改测试治理规则本身。
   - 修改公共 fixture 或全局 pytest 配置。

   ```bash
   scripts/test_full.sh
   ```

9. `scripts/test_durations.sh` 只用于测试治理和慢测试诊断，不得作为普通开发默认命令。

每次回复用户时必须说明：

- 本次改了什么范围。
- 根据矩阵选择了哪些测试。
- 本次跑了哪些测试。
- 没有跑哪些测试。
- 未跑 full regression 的原因。
- 如果发版前仍建议 full regression，必须明确提醒。
