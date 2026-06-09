"""Analyze reference-style evidence without importing product facts."""

from __future__ import annotations

import json
from collections.abc import Sequence

from docforge_core.domain.enums import AllowedUsage, CorpusType, NextAction, WorkflowStatus
from docforge_core.domain.schemas import DocForgeState, EvidenceItem, ReferenceStyleProfile
from docforge_core.evidence.qdrant_store import QdrantStore
from docforge_core.io.state_store import StateStore
from docforge_core.llm.base import LLMProvider
from docforge_core.llm.prompt_loader import load_prompt
from docforge_core.llm.provider_factory import create_llm_provider

from ._shared import filtered_evidence, generate_json, transition

DEFAULT_REFERENCE_STYLE = ReferenceStyleProfile(
    writing_style="用户操作手册型软著文档，语言应客观、克制、避免宣传式表达。",
    screenshot_usage_pattern="优先在核心功能章节插入产品界面截图，并使用“图 x-x xxx”的图片说明。",
    operation_step_pattern="按用户操作顺序描述入口、页面、按钮、结果。",
    prohibited_content_warning=[
        "未提供参考软著资料，系统不得虚构参考文档结构。",
        "不得使用参考资料中的产品事实作为当前产品事实。",
    ],
)
GENERIC_STYLE_TERMS = (
    "引言",
    "软件概述",
    "运行环境",
    "登录",
    "首页",
    "功能说明",
    "核心功能",
    "操作流程",
    "系统管理",
    "用户管理",
    "权限管理",
    "数据管理",
    "常见问题",
    "附录",
    "截图",
    "步骤",
    "章节",
    "目录",
    "说明",
)
REFERENCE_POLLUTION_TERMS = ("参考产品", "对方产品", "秘密模块", "专有模块")
FILTER_WARNING = "已过滤疑似参考软著产品事实内容，避免污染当前产品事实。"


class ReferenceStyleAgent:
    """Produce ReferenceStyleProfile from style-only evidence."""

    def __init__(
        self,
        state_store: StateStore | None = None,
        qdrant_store: QdrantStore | None = None,
        llm_provider: LLMProvider | None = None,
        top_k: int = 6,
    ) -> None:
        self.state_store = state_store or StateStore()
        self.qdrant_store = qdrant_store
        self.llm_provider = llm_provider
        self.top_k = top_k

    def analyze_run(self, run_id: str) -> DocForgeState:
        state = self.state_store.load_state(run_id)
        evidence = filtered_evidence(
            state,
            CorpusType.REFERENCE_STYLE,
            AllowedUsage.STYLE_ONLY,
        )[: self.top_k]
        profile = DEFAULT_REFERENCE_STYLE.model_copy(deep=True)

        if evidence:
            try:
                provider = self.llm_provider or create_llm_provider()
                result = generate_json(provider, load_prompt("reference_style.md"), evidence)
                profile = ReferenceStyleProfile.model_validate(
                    {**profile.model_dump(), **result}
                )
                profile = self._sanitize_reference_style_profile(profile, evidence)
            except (ValueError, TypeError) as exc:
                if "API_KEY" in str(exc):
                    raise
                state.warnings.append(f"ReferenceStyleAgent 使用保守默认结果: {exc}")

        state.style_profile = profile
        transition(
            state,
            WorkflowStatus.EVIDENCE_MAPPED,
            WorkflowStatus.REFERENCE_STYLE_ANALYZED,
            NextAction.UNDERSTAND_PRODUCT,
            "ReferenceStyleAgent.analyze_run",
            "reference style analyzed",
        )
        self.state_store.save_state(state)
        return state

    @staticmethod
    def _sanitize_reference_style_profile(
        profile: ReferenceStyleProfile,
        evidence: Sequence[EvidenceItem],
    ) -> ReferenceStyleProfile:
        """Keep only generic structure and writing patterns from reference output."""
        filtered = False
        reference_text = " ".join(
            [item.summary or "" for item in evidence] + [tag for item in evidence for tag in item.tags]
        ).lower()

        def sanitize_patterns(patterns: list[dict[str, object]]) -> list[dict[str, object]]:
            nonlocal filtered
            safe: list[dict[str, object]] = []
            for pattern in patterns:
                text = json.dumps(pattern, ensure_ascii=False).lower()
                has_risk = any(term.lower() in text for term in REFERENCE_POLLUTION_TERMS)
                is_generic = any(term.lower() in text for term in GENERIC_STYLE_TERMS)
                copies_reference_content = any(
                    isinstance(value, str)
                    and len(value) >= 4
                    and value.lower() in reference_text
                    and not any(term.lower() in value.lower() for term in GENERIC_STYLE_TERMS)
                    for value in pattern.values()
                )
                if has_risk or copies_reference_content or not is_generic:
                    filtered = True
                    continue
                safe.append(pattern)
            return safe

        profile.common_chapter_structure = sanitize_patterns(profile.common_chapter_structure)
        profile.reusable_outline_pattern = sanitize_patterns(profile.reusable_outline_pattern)

        for field, fallback in (
            ("writing_style", DEFAULT_REFERENCE_STYLE.writing_style),
            ("screenshot_usage_pattern", DEFAULT_REFERENCE_STYLE.screenshot_usage_pattern),
            ("operation_step_pattern", DEFAULT_REFERENCE_STYLE.operation_step_pattern),
        ):
            value = str(getattr(profile, field))
            if any(term.lower() in value.lower() for term in REFERENCE_POLLUTION_TERMS):
                setattr(profile, field, fallback)
                filtered = True

        if filtered and FILTER_WARNING not in profile.prohibited_content_warning:
            profile.prohibited_content_warning.append(FILTER_WARNING)
        return profile
