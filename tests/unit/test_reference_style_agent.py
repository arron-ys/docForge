from pathlib import Path

from docforge_core.agents.reference_style_agent import ReferenceStyleAgent
from docforge_core.domain.enums import NextAction, WorkflowStatus
from docforge_core.llm.mock_provider import MockLLMProvider

from .agent_helpers import product_evidence, reference_evidence, save_state


def test_no_reference_evidence_uses_conservative_default(tmp_path: Path) -> None:
    store, state = save_state(tmp_path, WorkflowStatus.EVIDENCE_MAPPED, [product_evidence()])

    result = ReferenceStyleAgent(state_store=store).analyze_run(state.run_id)

    assert result.style_profile.common_chapter_structure == []
    assert "不得虚构" in result.style_profile.prohibited_content_warning[0]
    assert result.workflow_status == WorkflowStatus.REFERENCE_STYLE_ANALYZED
    assert result.next_action == NextAction.UNDERSTAND_PRODUCT


def test_reference_agent_uses_only_reference_evidence_and_is_idempotent(tmp_path: Path) -> None:
    store, state = save_state(
        tmp_path,
        WorkflowStatus.EVIDENCE_MAPPED,
        [product_evidence(), reference_evidence()],
    )
    provider = MockLLMProvider(
        json_response={
            "writing_style": "客观操作手册",
            "common_chapter_structure": [{"title": "软件概述"}],
            "prohibited_content_warning": ["不得复用产品事实"],
        }
    )
    agent = ReferenceStyleAgent(state_store=store, llm_provider=provider)

    first = agent.analyze_run(state.run_id)
    second = agent.analyze_run(state.run_id)

    assert first.style_profile.writing_style == "客观操作手册"
    assert "秘密模块" not in first.style_profile.model_dump_json()
    logs = [item for item in second.status_history if item.node_name == "ReferenceStyleAgent.analyze_run"]
    assert len(logs) == 1


def test_invalid_llm_json_falls_back_without_crashing(tmp_path: Path) -> None:
    store, state = save_state(tmp_path, WorkflowStatus.EVIDENCE_MAPPED, [reference_evidence()])
    provider = MockLLMProvider(json_response={"common_chapter_structure": "invalid"})

    result = ReferenceStyleAgent(state_store=store, llm_provider=provider).analyze_run(state.run_id)

    assert result.style_profile.common_chapter_structure == []
    assert result.warnings


def test_reference_specific_content_is_filtered_from_style_profile(tmp_path: Path) -> None:
    store, state = save_state(
        tmp_path,
        WorkflowStatus.EVIDENCE_MAPPED,
        [reference_evidence(summary="参考产品包含秘密模块，章节采用操作手册写法")],
    )
    provider = MockLLMProvider(
        json_response={
            "common_chapter_structure": [{"title": "秘密模块"}],
            "reusable_outline_pattern": [{"title": "参考产品专有模块"}],
        }
    )

    result = ReferenceStyleAgent(state_store=store, llm_provider=provider).analyze_run(state.run_id)

    assert result.style_profile.common_chapter_structure == []
    assert result.style_profile.reusable_outline_pattern == []
    assert any("已过滤疑似参考软著产品事实内容" in item for item in result.style_profile.prohibited_content_warning)
