"""Shared title normalization and forbidden-feature matching."""

import re

FORBIDDEN_FEATURE_PREFIXES = (
    "证据不足：",
    "证据不足:",
    "规划中：",
    "规划中:",
    "状态待确认：",
    "状态待确认:",
)
TITLE_PUNCTUATION_PATTERN = re.compile(r"[\s：:\-—_（）()【】\[\]]+")


def normalize_title(text: str) -> str:
    return TITLE_PUNCTUATION_PATTERN.sub("", text.strip()).lower()


def is_forbidden_title(title: str, forbidden_names: list[str]) -> bool:
    normalized_title = normalize_title(title)
    if not normalized_title:
        return False
    for forbidden_name in forbidden_names:
        candidates = [forbidden_name]
        stripped = forbidden_name.strip()
        for prefix in FORBIDDEN_FEATURE_PREFIXES:
            if stripped.startswith(prefix):
                candidates.append(stripped.removeprefix(prefix))
                break
        if any(
            normalized and normalized in normalized_title
            for normalized in (normalize_title(candidate) for candidate in candidates)
        ):
            return True
    return False
