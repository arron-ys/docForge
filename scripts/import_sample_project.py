#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from docforge_core.io.state_store import StateStore
from docforge_core.workflow.e2e_sample_runner import (
    default_e2e_sample_dir,
    load_e2e_sample_project,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create a run and import the built-in DocForge E2E sample project.",
    )
    parser.add_argument(
        "--run-id",
        help="Import into an existing run_id. If omitted, a new run is created.",
    )
    parser.add_argument(
        "--project-name",
        default="DocForge E2E Sample",
        help="Project name to use when creating a new run.",
    )
    parser.add_argument(
        "--sample-dir",
        type=Path,
        default=default_e2e_sample_dir(),
        help="Path to the sample fixture directory.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    store = StateStore()

    if args.run_id:
        run_id = args.run_id
        store.load_state(run_id)
        created_new_run = False
    else:
        state = store.create_initial_state(project_name=args.project_name)
        run_id = state.run_id
        created_new_run = True

    result = load_e2e_sample_project(store, run_id, sample_dir=args.sample_dir)

    print(f"run_id={result.run_id}")
    print(f"sample_dir={Path(args.sample_dir).resolve()}")
    print(f"imported_count={result.imported_count}")
    print(f"skipped_existing={str(result.skipped_existing).lower()}")
    print(f"created_new_run={str(created_new_run).lower()}")
    print(f"run_state={store.data_dir / 'runs' / result.run_id / 'state.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
