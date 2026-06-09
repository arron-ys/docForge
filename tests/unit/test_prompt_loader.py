from pathlib import Path

import pytest

from docforge_core.llm.prompt_loader import load_prompt


def test_load_prompt_reads_prompt_md_file() -> None:
    content = load_prompt("audit.md")

    assert "Audit" in content or "audit" in content.lower() or "Sprint" in content


def test_load_prompt_missing_file_raises_file_not_found() -> None:
    with pytest.raises(FileNotFoundError):
        load_prompt("missing.md")


def test_load_prompt_rejects_path_traversal() -> None:
    with pytest.raises(ValueError):
        load_prompt("../README.md")


def test_load_prompt_rejects_absolute_path() -> None:
    with pytest.raises(ValueError):
        load_prompt(str(Path("/tmp/audit.md")))


def test_load_prompt_rejects_non_md_file() -> None:
    with pytest.raises(ValueError):
        load_prompt("audit.txt")
