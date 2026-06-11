"""Persisted workspace strategy preferences for a run."""

from __future__ import annotations

from typing import Any

from docforge_core.domain.schemas import DocForgeState

SETTINGS_KEY = "workspace_settings"

DEFAULT_RUN_SETTINGS: dict[str, str] = {
    "product_type_hint": "agent_decide",
    "doc_output_type": "product_feature_description",
    "reference_style_strength": "medium",
}

PRODUCT_TYPE_LABELS: dict[str, str] = {
    "saas_web_platform": "SaaS / Web 平台",
    "ai_platform": "AI 平台",
    "data_platform": "数据平台",
    "industrial_software": "工业软件",
    "tool_software": "工具软件",
    "agent_decide": "让 Agent 根据资料判断",
}

DOC_OUTPUT_TYPE_LABELS: dict[str, str] = {
    "user_manual": "用户操作手册型软著",
    "product_feature_description": "产品功能说明型软著",
    "technical_design": "技术设计说明型软著",
}

REFERENCE_STYLE_STRENGTH_LABELS: dict[str, str] = {
    "weak": "弱参考",
    "medium": "中参考",
    "strong": "强参考",
}


def get_run_settings(state: DocForgeState) -> dict[str, str]:
    raw_settings = state.output_requirements.get(SETTINGS_KEY, {})
    settings = dict(DEFAULT_RUN_SETTINGS)
    if isinstance(raw_settings, dict):
        for key in DEFAULT_RUN_SETTINGS:
            value = raw_settings.get(key)
            if isinstance(value, str):
                settings[key] = value
    return normalize_run_settings(settings)


def set_run_settings(state: DocForgeState, settings: dict[str, Any]) -> None:
    normalized = normalize_run_settings(settings)
    state.output_requirements[SETTINGS_KEY] = normalized


def normalize_run_settings(settings: dict[str, Any]) -> dict[str, str]:
    normalized = dict(DEFAULT_RUN_SETTINGS)
    product_type_hint = settings.get("product_type_hint")
    if isinstance(product_type_hint, str) and product_type_hint in PRODUCT_TYPE_LABELS:
        normalized["product_type_hint"] = product_type_hint

    doc_output_type = settings.get("doc_output_type")
    if isinstance(doc_output_type, str) and doc_output_type in DOC_OUTPUT_TYPE_LABELS:
        normalized["doc_output_type"] = doc_output_type

    reference_style_strength = settings.get("reference_style_strength")
    if (
        isinstance(reference_style_strength, str)
        and reference_style_strength in REFERENCE_STYLE_STRENGTH_LABELS
    ):
        normalized["reference_style_strength"] = reference_style_strength
    return normalized


def product_type_label(value: str) -> str:
    return PRODUCT_TYPE_LABELS.get(value, value)


def doc_output_type_label(value: str) -> str:
    return DOC_OUTPUT_TYPE_LABELS.get(value, value)


def reference_style_strength_label(value: str) -> str:
    return REFERENCE_STYLE_STRENGTH_LABELS.get(value, value)
