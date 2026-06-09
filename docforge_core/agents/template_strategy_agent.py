"""Recommend a template strategy without freezing a document plan."""

from __future__ import annotations

from docforge_core.domain.enums import NextAction, WorkflowStatus
from docforge_core.domain.schemas import DocForgeState, TemplateStrategy
from docforge_core.io.state_store import StateStore
from docforge_core.llm.base import LLMProvider

from ._shared import AI_NON_CURRENT_RISK_PREFIX, transition, unique_strings

EXCLUDED_TEMPLATES = [
    "TEMPLATE_BACKEND_API_TECHNICAL",
    "TEMPLATE_EMBEDDED_SOFTWARE_DESIGN",
    "TEMPLATE_ALGORITHM_PAPER_STYLE",
]
WEB_BASE_CHAPTERS = [
    "引言",
    "软件概述",
    "运行环境",
    "登录与首页",
    "核心功能说明",
    "用户操作流程",
    "常见问题与附录",
]
DATA_PLATFORM_CHAPTERS = [
    "数据资产管理",
    "数据集管理",
    "数据导入与处理",
    "质量检查与报告",
]
AI_BASE_CHAPTER = "模型相关功能"
AI_TRAINING_EVALUATION_CHAPTER = "训练或评测相关功能"
PERMISSION_CHAPTER = "用户与权限管理"
AUTOMOTIVE_OPTIONAL_CHAPTER = "汽车行业数据对象说明"


class TemplateStrategyAgent:
    """Recommend, but never freeze, a soft-copyright document strategy."""

    def __init__(
        self,
        state_store: StateStore | None = None,
        llm_provider: LLMProvider | None = None,
    ) -> None:
        self.state_store = state_store or StateStore()
        self.llm_provider = llm_provider

    def recommend_run(self, run_id: str) -> DocForgeState:
        state = self.state_store.load_state(run_id)
        state.template_strategy = self._recommend(state)
        transition(
            state,
            WorkflowStatus.DIAGNOSED,
            WorkflowStatus.TEMPLATE_RECOMMENDED,
            NextAction.ASK_HUMAN_CONFIRMATION,
            "TemplateStrategyAgent.recommend_run",
            "template strategy recommended",
        )
        self.state_store.save_state(state)
        return state

    @staticmethod
    def _recommend(state: DocForgeState) -> TemplateStrategy:
        diagnosis = state.diagnosis_result
        if diagnosis is None or diagnosis.primary_type == "待确认":
            return TemplateStrategy(
                base_template_id="TEMPLATE_PENDING_CONFIRMATION",
                base_template_name="待用户确认的软件类型模板",
                excluded_template_ids=EXCLUDED_TEMPLATES,
                risk_chapters=["软件类型待确认", "核心功能证据不足", "产品资料待补充"],
                recommendation_reason=["当前产品证据不足，模板需在用户补充资料后确认。"],
            )

        is_web = diagnosis.primary_type == "Web/SaaS 平台"
        recommended = list(
            WEB_BASE_CHAPTERS
            if is_web
            else ["引言", "软件概述", "运行环境", "核心功能说明"]
        )
        packs: list[str] = []
        optional: list[str] = []
        risks = list(diagnosis.risk_notes)
        reasons = list(diagnosis.diagnosis_reasons)
        has_ai_risk = any(
            note.startswith(AI_NON_CURRENT_RISK_PREFIX) for note in diagnosis.risk_notes
        )

        if "数据平台" in diagnosis.enhancement_tags:
            packs.append("PACK_DATA_PLATFORM")
            recommended.extend(DATA_PLATFORM_CHAPTERS)
        if "AI 平台" in diagnosis.enhancement_tags:
            packs.append("PACK_AI_LIGHT")
            recommended.append(AI_BASE_CHAPTER)
            if has_ai_risk:
                risks.append(AI_TRAINING_EVALUATION_CHAPTER)
            else:
                recommended.append(AI_TRAINING_EVALUATION_CHAPTER)
        elif has_ai_risk:
            risks.append("AI 能力当前版本状态待确认")
        if "权限管理" in diagnosis.enhancement_tags:
            packs.append("PACK_PERMISSION_MANAGEMENT")
            recommended.append(PERMISSION_CHAPTER)
        if "汽车工业软件" in diagnosis.enhancement_tags:
            packs.append("PACK_AUTO_INDUSTRIAL_SOFTWARE")
            optional.append(AUTOMOTIVE_OPTIONAL_CHAPTER)

        return TemplateStrategy(
            base_template_id=(
                "TEMPLATE_WEB_SAAS_USER_MANUAL" if is_web else "TEMPLATE_GENERAL_FUNCTIONAL"
            ),
            base_template_name=(
                "Web/SaaS 用户操作手册型软著文档" if is_web else "通用功能说明型软著文档"
            ),
            enhancement_pack_ids=unique_strings(packs),
            excluded_template_ids=EXCLUDED_TEMPLATES,
            recommended_chapters=unique_strings(recommended),
            optional_chapters=unique_strings(optional),
            risk_chapters=unique_strings(risks),
            recommendation_reason=unique_strings(reasons or ["根据软件类型诊断结果推荐模板。"]),
        )
