"""DocForge launcher entry.

保留 `app/main.py` 作为仓库级 Python 启动入口，但不再承载 Streamlit UI。

- 作为模块导入时，暴露 `api.main.app`，便于沿用 `uvicorn app.main:app` 形式。
- 作为脚本执行时，转发到 `scripts/dev.sh`，统一启动 FastAPI 与 Vue 前端。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from api.main import app

ROOT_DIR = Path(__file__).resolve().parents[1]
DEV_SCRIPT = ROOT_DIR / "scripts" / "dev.sh"


def main() -> int:
    if not DEV_SCRIPT.is_file():
        print(f"[app.main] missing launcher script: {DEV_SCRIPT}", file=sys.stderr)
        return 1

    os.execvp("bash", ["bash", str(DEV_SCRIPT)])
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
