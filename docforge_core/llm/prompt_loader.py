"""Prompt loader."""

from pathlib import Path

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


def load_prompt(name: str) -> str:
    prompt_name = Path(name)
    if prompt_name.is_absolute() or ".." in prompt_name.parts:
        raise ValueError("prompt 名称不允许路径穿越或绝对路径")
    if prompt_name.suffix != ".md":
        raise ValueError("只能读取 .md prompt 文件")

    path = PROMPTS_DIR / prompt_name
    resolved_path = path.resolve()
    if PROMPTS_DIR.resolve() not in resolved_path.parents:
        raise ValueError("prompt 路径必须位于 prompts 目录下")
    if not resolved_path.exists():
        raise FileNotFoundError(resolved_path)
    return resolved_path.read_text(encoding="utf-8")
