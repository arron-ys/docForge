"""Shared isolation and state-transition helpers for Sprint 6 agents."""

from __future__ import annotations

import json
from typing import Any

from docforge_core.domain.enums import AllowedUsage, CorpusType, NextAction, WorkflowStatus
from docforge_core.domain.schemas import DocForgeState, EvidenceItem, StateTransitionLog
from docforge_core.llm.base import LLMMessage, LLMProvider

AI_NON_CURRENT_RISK_PREFIX = (
    "AI 能力仅出现在规划中或证据不足内容中，不能判定为当前版本已实现功能。"
)


def filtered_evidence(
    state: DocForgeState,
    corpus_type: CorpusType,
    allowed_usage: AllowedUsage,
) -> list[EvidenceItem]:
    """Return only evidence that matches both isolation fields."""
    return [
        item
        for item in state.evidence_map
        if item.corpus_type == corpus_type and item.allowed_usage == allowed_usage
    ]


def evidence_context(evidence: list[EvidenceItem]) -> str:
    """Serialize compact evidence summaries without loading original documents."""
    payload = [
        {
            "evidence_id": item.evidence_id,
            "source_id": item.source_id,
            "evidence_type": item.evidence_type.value,
            "summary": item.summary,
            "tags": item.tags,
            "extracted_facts": item.extracted_facts,
        }
        for item in evidence
    ]
    return json.dumps(payload, ensure_ascii=False, indent=2)


def generate_json(
    provider: LLMProvider,
    system_prompt: str,
    evidence: list[EvidenceItem],
) -> dict[str, Any]:
    return provider.generate_json(
        [
            LLMMessage(role="system", content=system_prompt),
            LLMMessage(role="user", content=evidence_context(evidence)),
        ]
    )


def transition(
    state: DocForgeState,
    from_status: WorkflowStatus,
    to_status: WorkflowStatus,
    next_action: NextAction,
    node_name: str,
    reason: str,
) -> None:
    """Apply an exact-state transition once."""
    if state.workflow_status != from_status:
        return
    state.status_history.append(
        StateTransitionLog(
            from_status=from_status,
            to_status=to_status,
            node_name=node_name,
            reason=reason,
        )
    )
    state.workflow_status = to_status
    state.next_action = next_action


def unique_strings(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))
