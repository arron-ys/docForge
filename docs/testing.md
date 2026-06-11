# 测试策略

本文定义墨衡 DocForge 的测试分层、pytest markers 和日常开发测试命令。

## Python 解释器

本项目所有 Python 测试默认使用项目虚拟环境：

```bash
.venv/bin/python
```

不要把裸 `python` 或全局 `python3` 作为项目测试入口。原因是系统或全局解释器不保证安装了 DocForge 的开发依赖，也不保证依赖版本与项目一致。`python: command not found` 不需要通过切换到 `python3 -m pytest` 解决；正确做法是使用 `scripts/test_*.sh` 或显式调用 `.venv/bin/python -m pytest ...`。

如果 `.venv/bin/python` 不存在，先重建虚拟环境：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"
```

这里的 `python3 -m venv` 只用于创建项目虚拟环境；测试命令仍然使用 `.venv/bin/python`。

## 分层

- `unit`：单函数、单服务、单 agent、单状态转换；不访问网络、不调用真实 LLM、不依赖真实 API Key、不生成大型文件。普通开发常跑。
- `contract`：API 响应结构、workflow 状态枚举、`next_action`、错误码、前后端契约字段。普通开发常跑。
- `smoke`：最小核心链路，验证上传样例资料后可解析、可推进到人工确认、确认后可导出并返回可下载 DOCX 信息。主流程相关改动后运行。
- `integration`：多模块协作、完整 workflow、完整 DOCX 导出、diagnostics + state + artifact。默认不在每轮开发中全量运行。
- `slow`：大文件、多 fixture、完整文档导出或明显慢于普通单测的测试。默认从开发期测试中排除。
- `external`：真实 API Key、网络、LLM 或第三方服务。默认从开发期测试中排除。
- `legacy`：暂时保留的废弃行为测试。需要写明保留原因和后续处理建议；不得长期存在。

`tests/conftest.py` 会根据目录自动添加基础 marker：`tests/unit` 加 `unit`，`tests/contract` 加 `contract`，`tests/smoke` 加 `smoke`，`tests/integration` 加 `integration` 和 `slow`。

## 标准命令

测试脚本可以从任意目录调用，脚本会自动切到项目根目录；内部不会 fallback 到全局 `python3`。如果 `.venv/bin/python` 不可用，脚本会直接失败并输出修复建议。

收集测试：

```bash
scripts/test_collect.sh
```

快速基线：

```bash
scripts/test_quick.sh
```

`scripts/test_quick.sh` 是普通开发默认快速基线，覆盖 API 契约、schema/state、用户可读错误和 diagnostics。它不跑全部 unit、不跑 integration、不跑 smoke，也不跑 durations。

前端验证：

```bash
scripts/test_frontend.sh
```

`scripts/test_frontend.sh` 是前端代码变更的统一验证入口，会进入 `frontend/docforge-web` 并运行 `pnpm run build`。它使用 Node.js/pnpm 工具链，不调用 Python `.venv`；如果 `pnpm` 不可用，需要修复 Node.js/Corepack 环境，不要把 pnpm 安装到 Python 虚拟环境。

中等范围后端回归：

```bash
scripts/test_dev.sh
```

等价命令：

```bash
.venv/bin/python -m pytest tests/unit tests/contract -m "not slow and not external and not legacy" -q
```

`scripts/test_dev.sh` 会始终运行 `tests/unit`，并在 `tests/contract` 存在时自动加入 contract 测试。这样分支上暂未建立 contract 目录时也不会引用不存在路径。

`scripts/test_dev.sh` 不是每次普通开发默认命令。只有改动涉及后端核心共享逻辑、多个 unit 模块、API 契约或状态模型时才运行。

冒烟测试：

```bash
scripts/test_smoke.sh
```

集成测试：

```bash
scripts/test_integration.sh
```

全量回归：

```bash
scripts/test_full.sh
```

上次失败：

```bash
scripts/test_lf.sh
```

慢测试统计：

```bash
scripts/test_durations.sh
```

`scripts/test_durations.sh` 是测试治理和慢测试诊断专用命令，不进入普通开发默认流程。

## Full Regression 触发条件

只有以下情况才默认运行 full regression：

- 用户明确要求。
- Sprint 完成。
- Release Candidate 审计。
- 修改核心架构。
- 修改全局状态机。
- 修改测试治理规则本身。
- 修改公共 fixture 或全局 pytest 配置。

普通业务开发应先查看 `git diff --name-only`，再根据 [docs/test_impact_matrix.md](test_impact_matrix.md) 选择最小必要测试。默认只跑受影响测试文件；前端改动跑 `scripts/test_frontend.sh`；需要基础后端基线时跑 `scripts/test_quick.sh`。不要默认跑 `scripts/test_dev.sh`，更不要默认跑 `scripts/test_full.sh`；涉及主链路再跑 `scripts/test_smoke.sh`；涉及 workflow、evidence、DOCX、diagnostics、artifact 或公共 fixture 时再补相关 integration。

## Contract / Smoke 规划

当前测试分层已经预留并注册 `contract` 和 `smoke` marker。`tests/contract` 用于 API/schema/status 契约，`tests/smoke` 用于最小核心链路。后续新增前后端契约或主流程冒烟用例时，应优先放入对应目录，而不是继续堆在 `tests/unit`。
