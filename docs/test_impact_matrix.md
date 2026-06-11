# 测试影响矩阵

本矩阵用于决定普通开发后的最小必要测试。默认先看 `git diff --name-only`，再按影响范围选择测试；不要每次默认运行 `scripts/test_dev.sh` 或 `scripts/test_full.sh`。

## 默认流程

1. 先运行与修改文件直接相关的测试。
2. 需要基础后端契约/状态基线时，运行 `scripts/test_quick.sh`。
3. 只有影响后端核心共享逻辑、多个 unit 模块、API 契约或状态模型时，运行 `scripts/test_dev.sh`。
4. 只有影响上传、解析、人工确认、状态推进、导出主链路时，运行 `scripts/test_smoke.sh`。
5. 只有测试治理、核心架构、全局状态机、公共 fixture 等变更才默认 full regression。

## 矩阵

| 修改范围 | 应运行 | 不默认运行 | 说明 |
| --- | --- | --- | --- |
| 只改 `docs/**`、`README.md`、说明文案 | `git diff --check`；通常不需要 pytest | `scripts/test_quick.sh`、`scripts/test_dev.sh`、`scripts/test_smoke.sh`、`scripts/test_full.sh` | 文档变更不应触发 Python 回归。 |
| 只改 `frontend/docforge-web/src` 的 UI 文案、样式、组件布局 | `scripts/test_frontend.sh` | pytest、`scripts/test_dev.sh`、`scripts/test_full.sh` | 不涉及后端契约时不跑 Python 测试。 |
| 改前端 API 调用、状态映射、action 映射 | `scripts/test_frontend.sh`；`tests/contract/test_api_sprint2.py`；影响上传、解析、人工确认、导出等主链路时跑 `scripts/test_smoke.sh` | `scripts/test_full.sh` | API 字段消费要验证后端契约。 |
| 改 `api/**` | `tests/contract/test_api_sprint2.py`；相关 unit；影响主流程时 `scripts/test_smoke.sh` | `scripts/test_full.sh` | 优先保护响应结构、错误码和 action guard。 |
| 改 `app/main.py` 或启动入口 | `scripts/test_quick.sh`；必要时 contract / smoke | `scripts/test_full.sh` | 入口变更先跑轻量基线，再按影响升级。 |
| 改 `docforge_core/workflow/**` | `tests/unit/test_workflow_orchestrator.py`；`tests/unit/test_workflow_diagnostics.py`；相关 human confirm / revision loop 单测；主流程变更跑 smoke；状态机深改跑 integration 或 full | 默认不跑 full | workflow 是高风险区，按状态机影响升级。 |
| 改 `docforge_core/exporters/**` 或 DOCX 导出相关代码 | `tests/unit/test_docx_exporter.py`；`tests/unit/test_docx_acceptance_checker.py`；必要时 `tests/integration/test_artifact_level_e2e.py` | 默认不跑 full | 导出安全和可下载 artifact 优先点跑。 |
| 改 evidence / parsing / source / frozen plan 相关代码 | `tests/unit/test_evidence_extractor.py`；`tests/unit/test_source_parsing_service.py`；`tests/unit/test_frozen_doc_plan_service.py`；必要时 smoke 或 upload-level integration | 默认不跑 full | 证据边界和资料解析需要对应单测保护。 |
| 改 prompt / writer / outline / audit 相关代码 | 对应 agent 单测，例如 writer / outline / audit / quality gate；影响最终文档生成链路时跑 smoke | 默认不跑 full | 先点跑 agent，再按主链路影响升级。 |
| 改 `tests/conftest.py`、`pyproject.toml`、`scripts/test_*.sh`、公共 fixtures | `scripts/test_collect.sh`；`scripts/test_quick.sh`；`scripts/test_dev.sh`；`scripts/test_full.sh` | 无 | 测试治理规则本身变化，必须全量验证。 |

## 命令定位

- `scripts/test_quick.sh`：普通开发默认快速基线，只覆盖 API 契约、schema/state、用户可读错误和 diagnostics。
- `scripts/test_frontend.sh`：前端统一验证入口，运行 `frontend/docforge-web` 的 `pnpm run build`。
- `scripts/test_dev.sh`：中等范围后端回归，运行 unit + contract，不是每次普通开发默认命令。
- `scripts/test_smoke.sh`：主链路冒烟。
- `scripts/test_integration.sh`：跨模块、artifact、DOCX、workflow 深改后的验证。
- `scripts/test_full.sh`：Sprint 完成、Release Candidate、测试治理变更、核心架构变更时运行。
- `scripts/test_durations.sh`：测试治理和慢测试诊断专用，不进入普通开发默认流程。
