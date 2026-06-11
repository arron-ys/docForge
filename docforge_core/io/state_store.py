"""
StateStore — state.json 读写管理。

MVP 阶段主状态源为 data/runs/{run_id}/state.json。
当前 v0.1 主流程由 WorkflowOrchestratorService 调度；LangGraph scaffold 仅保留为未来 observability /
tracing 预留能力。state.json 负责业务状态持久化，Qdrant 负责证据语义检索。

序列化规则：
- UTF-8 编码
- 保留中文（ensure_ascii=False）
- JSON 缩进 2 空格
- 使用 Pydantic model_dump(mode='json') 转换后由标准库 json 序列化
- 读取时必须经过 Pydantic model_validate 重新校验
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from docforge_core.domain.enums import NextAction, SourceType, WorkflowStatus
from docforge_core.domain.schemas import DocForgeState, SourceItem, StateTransitionLog

from .run_paths import (
    ensure_run_dirs,
    generate_run_id,
    get_state_file,
)


class StateStore:
    """
    state.json 的 CRUD 封装。

    Args:
        data_dir: 数据根目录。None 时从 Settings 读取 docforge_data_dir。
                  传入显式路径（如 pytest tmp_path）便于测试。
    """

    def __init__(self, data_dir: Path | None = None) -> None:
        if data_dir is not None:
            self._data_dir: Path | None = data_dir
        else:
            self._data_dir = None  # 懒加载，避免在测试外过早读 settings

    def _get_data_dir(self) -> Path:
        if self._data_dir is not None:
            return self._data_dir
        from docforge_core.config.settings import get_settings

        return get_settings().docforge_data_dir

    @property
    def data_dir(self) -> Path:
        """Resolved data root used by this store."""
        return self._get_data_dir()

    # ── 公共接口 ──────────────────────────────────────────────────────────

    def create_initial_state(self, project_name: str | None = None) -> DocForgeState:
        """
        创建初始 DocForgeState 并落盘（同时建立 run 目录树）。

        Returns:
            已保存的 DocForgeState 实例。
        """
        run_id = generate_run_id()
        data_dir = self._get_data_dir()
        ensure_run_dirs(run_id, data_dir)

        state = DocForgeState(
            run_id=run_id,
            project_name=project_name or "",
        )
        self.save_state(state)
        return state

    def save_state(self, state: DocForgeState) -> Path:
        """
        将 DocForgeState 序列化并写入 state.json。

        Returns:
            state.json 的 Path。
        """
        data_dir = self._get_data_dir()
        state_file = get_state_file(state.run_id, data_dir)
        state_file.parent.mkdir(parents=True, exist_ok=True)

        payload: dict[str, Any] = state.model_dump(mode="json")
        state_file.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return state_file

    def load_state(self, run_id: str) -> DocForgeState:
        """
        从 state.json 加载并经 Pydantic 重新校验。

        Raises:
            FileNotFoundError: state.json 不存在。
            ValidationError: 数据不符合 DocForgeState 约束。
        """
        data_dir = self._get_data_dir()
        state_file = get_state_file(run_id, data_dir)

        if not state_file.exists():
            raise FileNotFoundError(f"state.json 不存在: {state_file}")

        raw = state_file.read_text(encoding="utf-8")
        payload: dict[str, Any] = json.loads(raw)
        return DocForgeState.model_validate(payload)

    def update_state(self, run_id: str, **updates: Any) -> DocForgeState:
        """
        局部更新 state.json。

        1. 加载当前状态；
        2. 用 **updates 覆盖指定字段；
        3. 经 Pydantic 重新校验；
        4. 保存并返回更新后的状态。

        Raises:
            FileNotFoundError: state.json 不存在。
            ValidationError: 更新后数据不符合约束。
        """
        state = self.load_state(run_id)
        current: dict[str, Any] = state.model_dump(mode="json")
        current.update(updates)
        new_state = DocForgeState.model_validate(current)
        self.save_state(new_state)
        return new_state

    def add_source_item(self, run_id: str, source_item: SourceItem) -> DocForgeState:
        """
        Append a SourceItem to state.json and maintain source id indexes.

        Raises:
            ValueError: source_id already exists in source_registry.
        """
        state = self.load_state(run_id)
        existing_ids = {item.source_id for item in state.source_registry}
        if source_item.source_id in existing_ids:
            raise ValueError(f"source_id 已存在: {source_item.source_id}")

        state.source_registry.append(source_item)

        if source_item.is_reference_source:
            state.reference_source_ids.append(source_item.source_id)
        if source_item.is_product_source:
            state.product_source_ids.append(source_item.source_id)
        if source_item.source_type == SourceType.SCREENSHOT:
            state.screenshot_source_ids.append(source_item.source_id)

        if state.workflow_status == WorkflowStatus.CREATED:
            state.status_history.append(
                StateTransitionLog(
                    from_status=WorkflowStatus.CREATED,
                    to_status=WorkflowStatus.MATERIAL_UPLOADED,
                    node_name="StateStore.add_source_item",
                    reason="source material uploaded",
                )
            )
            state.workflow_status = WorkflowStatus.MATERIAL_UPLOADED
            state.next_action = NextAction.PARSE_SOURCES

        self.save_state(state)
        return state

    # ── 便捷读取（不经过 Pydantic，用于快速调试） ─────────────────────────

    def read_raw(self, run_id: str) -> dict[str, Any]:
        """读取 state.json 的原始字典（不经过 Pydantic 校验，仅用于调试）。"""
        data_dir = self._get_data_dir()
        state_file = get_state_file(run_id, data_dir)
        if not state_file.exists():
            raise FileNotFoundError(f"state.json 不存在: {state_file}")
        return json.loads(state_file.read_text(encoding="utf-8"))
