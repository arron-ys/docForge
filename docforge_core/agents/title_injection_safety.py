"""Reject writer instruction injection embedded in outline titles."""

from .writing_goal_safety import contains_unsafe_instruction


def validate_outline_title_safe(title: str) -> None:
    """Require a nonempty title without high-risk writer instructions."""
    if not title.strip():
        raise ValueError("outline title 不得为空")
    if contains_unsafe_instruction(title):
        raise ValueError("outline title 包含不安全写作指令")
