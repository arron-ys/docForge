from __future__ import annotations

from dataclasses import dataclass

from docforge_core.domain.enums import NextAction, WorkflowStatus
from docforge_core.domain.schemas import DocForgeState

from .errors import action_not_allowed


@dataclass(frozen=True, slots=True)
class ActionRule:
    endpoint_action: str
    allowed_statuses: frozenset[WorkflowStatus]
    allowed_next_actions: frozenset[NextAction]
    user_error: str


ACTION_RULES: dict[str, ActionRule] = {
    "next": ActionRule(
        endpoint_action="next",
        allowed_statuses=frozenset(
            status
            for status in WorkflowStatus
            if status
            not in {
                WorkflowStatus.CREATED,
                WorkflowStatus.USER_CONFIRM_REQUIRED,
                WorkflowStatus.FINAL_EXPORTED,
                WorkflowStatus.RISK_EXPORTED,
                WorkflowStatus.FAILED,
            }
        ),
        allowed_next_actions=frozenset(
            action
            for action in NextAction
            if action
            not in {
                NextAction.INGEST_MATERIALS,
                NextAction.ASK_HUMAN_CONFIRMATION,
                NextAction.STOP,
            }
        ),
        user_error="当前还不能自动推进，请先完成资料上传或人工确认。",
    ),
    "confirm-product-type": ActionRule(
        endpoint_action="confirm-product-type",
        allowed_statuses=frozenset({WorkflowStatus.USER_CONFIRM_REQUIRED}),
        allowed_next_actions=frozenset({NextAction.ASK_HUMAN_CONFIRMATION}),
        user_error="当前还不能确认产品类型，请先完成产品理解和推荐策略生成。",
    ),
    "confirm-doc-plan": ActionRule(
        endpoint_action="confirm-doc-plan",
        allowed_statuses=frozenset(
            {
                WorkflowStatus.USER_CONFIRM_REQUIRED,
                WorkflowStatus.USER_CONFIRMED,
                WorkflowStatus.PLAN_FROZEN,
                WorkflowStatus.OUTLINE_CREATED,
            }
        ),
        allowed_next_actions=frozenset(
            {
                NextAction.ASK_HUMAN_CONFIRMATION,
                NextAction.FREEZE_DOC_PLAN,
                NextAction.CREATE_OUTLINE,
                NextAction.RUN_PLAN_QUALITY_GATE,
            }
        ),
        user_error="当前还不能确认文档目录，请先完成产品类型和文档策略确认。",
    ),
    "export-final-docx": ActionRule(
        endpoint_action="export-final-docx",
        allowed_statuses=frozenset({WorkflowStatus.DRAFT_QUALITY_GATE_PASSED}),
        allowed_next_actions=frozenset({NextAction.EXPORT_DOCX, NextAction.EXPORT_FINAL_DOC}),
        user_error="当前还不能导出正常版 DOCX，请先完成正文生成和质量检查。",
    ),
    "export-risk-docx": ActionRule(
        endpoint_action="export-risk-docx",
        allowed_statuses=frozenset({WorkflowStatus.RISK_VERSION_READY}),
        allowed_next_actions=frozenset({NextAction.EXPORT_RISK_DOCX, NextAction.EXPORT_RISK_DOC}),
        user_error="当前还不能导出风险版 DOCX，请先完成正文生成和风险检查。",
    ),
}


class ActionGuard:
    def ensure_allowed(self, state: DocForgeState, endpoint_action: str) -> None:
        rule = ACTION_RULES[endpoint_action]
        if state.workflow_status not in rule.allowed_statuses:
            raise action_not_allowed(rule.user_error)
        if state.next_action not in rule.allowed_next_actions:
            raise action_not_allowed(rule.user_error)

