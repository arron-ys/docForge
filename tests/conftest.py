from __future__ import annotations

from pathlib import Path

import pytest


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Apply governance markers from the test directory layout."""
    for item in items:
        parts = set(Path(item.path).parts)
        if "unit" in parts:
            item.add_marker(pytest.mark.unit)
        if "contract" in parts:
            item.add_marker(pytest.mark.contract)
        if "smoke" in parts:
            item.add_marker(pytest.mark.smoke)
        if "integration" in parts:
            item.add_marker(pytest.mark.integration)
            item.add_marker(pytest.mark.slow)
