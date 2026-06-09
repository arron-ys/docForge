"""
Run 目录管理模块。

路径规则（data_dir 由 Settings 提供，默认为 data/）：
data/runs/{run_id}/
  sources/
    reference/
    product/
    screenshots/
  parsed/
  evidence/
  drafts/
  audits/
  exports/
  state.json

run_id 格式：YYYYMMDD_HHMMSS_xxxx（全小写、只含字母数字下划线、唯一）
示例：20260605_154523_a7f3
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime
from pathlib import Path


def generate_run_id() -> str:
    """生成唯一 run_id，格式：YYYYMMDD_HHMMSS_xxxx。"""
    ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    suffix = secrets.token_hex(2)  # 4 位十六进制
    return f"{ts}_{suffix}"


def _resolve_data_dir(data_dir: Path | None) -> Path:
    """解析 data_dir，未指定时从 Settings 读取。"""
    if data_dir is not None:
        return data_dir
    from docforge_core.config.settings import get_settings

    return get_settings().docforge_data_dir


# ─── 路径派生函数（全部接受可选 data_dir，便于测试覆盖） ──────────────────


def get_run_dir(run_id: str, data_dir: Path | None = None) -> Path:
    """data/runs/{run_id}/"""
    return _resolve_data_dir(data_dir) / "runs" / run_id


def get_sources_dir(run_id: str, data_dir: Path | None = None) -> Path:
    """data/runs/{run_id}/sources/"""
    return get_run_dir(run_id, data_dir) / "sources"


def get_reference_dir(run_id: str, data_dir: Path | None = None) -> Path:
    """data/runs/{run_id}/sources/reference/"""
    return get_sources_dir(run_id, data_dir) / "reference"


def get_product_dir(run_id: str, data_dir: Path | None = None) -> Path:
    """data/runs/{run_id}/sources/product/"""
    return get_sources_dir(run_id, data_dir) / "product"


def get_screenshots_dir(run_id: str, data_dir: Path | None = None) -> Path:
    """data/runs/{run_id}/sources/screenshots/"""
    return get_sources_dir(run_id, data_dir) / "screenshots"


def get_parsed_dir(run_id: str, data_dir: Path | None = None) -> Path:
    """data/runs/{run_id}/parsed/"""
    return get_run_dir(run_id, data_dir) / "parsed"


def get_evidence_dir(run_id: str, data_dir: Path | None = None) -> Path:
    """data/runs/{run_id}/evidence/"""
    return get_run_dir(run_id, data_dir) / "evidence"


def get_drafts_dir(run_id: str, data_dir: Path | None = None) -> Path:
    """data/runs/{run_id}/drafts/"""
    return get_run_dir(run_id, data_dir) / "drafts"


def get_audits_dir(run_id: str, data_dir: Path | None = None) -> Path:
    """data/runs/{run_id}/audits/"""
    return get_run_dir(run_id, data_dir) / "audits"


def get_exports_dir(run_id: str, data_dir: Path | None = None) -> Path:
    """data/runs/{run_id}/exports/"""
    return get_run_dir(run_id, data_dir) / "exports"


def get_state_file(run_id: str, data_dir: Path | None = None) -> Path:
    """data/runs/{run_id}/state.json"""
    return get_run_dir(run_id, data_dir) / "state.json"


def ensure_run_dirs(run_id: str, data_dir: Path | None = None) -> Path:
    """
    创建 run 目录树下所有子目录，返回 run_dir。

    跨平台安全（parents=True, exist_ok=True）。
    """
    run_dir = get_run_dir(run_id, data_dir)
    for sub in (
        get_reference_dir(run_id, data_dir),
        get_product_dir(run_id, data_dir),
        get_screenshots_dir(run_id, data_dir),
        get_parsed_dir(run_id, data_dir),
        get_evidence_dir(run_id, data_dir),
        get_drafts_dir(run_id, data_dir),
        get_audits_dir(run_id, data_dir),
        get_exports_dir(run_id, data_dir),
    ):
        sub.mkdir(parents=True, exist_ok=True)
    return run_dir
