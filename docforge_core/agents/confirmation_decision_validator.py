"""Shared validation for human-confirmed template decisions."""

from docforge_core.domain.schemas import TemplateConfirmationDecision, TemplateStrategy


def validate_template_confirmation_decision(
    decision: TemplateConfirmationDecision,
    strategy: TemplateStrategy,
) -> None:
    """Reject decisions that do not match the recommended template strategy."""
    if not decision.selected_top_level_chapters:
        raise ValueError("selected_top_level_chapters 不得为空")
    if decision.selected_base_template_id != strategy.base_template_id:
        raise ValueError("selected_base_template_id 与 template_strategy 不一致")
    if decision.selected_base_template_name != strategy.base_template_name:
        raise ValueError("selected_base_template_name 与 template_strategy 不一致")

    recommended_packs = set(strategy.enhancement_pack_ids)
    if not set(decision.selected_enhancement_pack_ids).issubset(recommended_packs):
        raise ValueError("selected_enhancement_pack_ids 包含未推荐的增强包")

    allowed_chapters = (
        set(strategy.recommended_chapters)
        | set(strategy.optional_chapters)
        | set(strategy.risk_chapters)
    )
    if not set(decision.selected_top_level_chapters).issubset(allowed_chapters):
        raise ValueError("selected_top_level_chapters 包含未知章节")
    if not set(decision.selected_optional_chapters).issubset(
        set(strategy.optional_chapters)
    ):
        raise ValueError("selected_optional_chapters 包含未知可选章节")
    if not set(decision.excluded_chapters).issubset(allowed_chapters):
        raise ValueError("excluded_chapters 包含未知章节")

    acknowledged_risks = set(decision.acknowledged_risk_chapters)
    strategy_risks = set(strategy.risk_chapters)
    if not acknowledged_risks.issubset(strategy_risks):
        raise ValueError("acknowledged_risk_chapters 包含未知风险章节")

    selected_risks = set(decision.selected_top_level_chapters) & strategy_risks
    if selected_risks and not decision.risk_acknowledged:
        raise ValueError("风险章节被选择时必须 risk_acknowledged=true")
    if strategy_risks and not decision.risk_acknowledged:
        raise ValueError("存在风险章节时必须先明确知晓风险")
    if selected_risks and not selected_risks.issubset(acknowledged_risks):
        raise ValueError("被选择的风险章节必须出现在 acknowledged_risk_chapters")
    if acknowledged_risks and not decision.risk_acknowledged:
        raise ValueError("承认风险章节时必须 risk_acknowledged=true")
