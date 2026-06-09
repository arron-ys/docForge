import pytest

from docforge_core.agents.section_draft_validator import SectionDraftValidator
from docforge_core.domain.schemas import SectionPlan

from .outline_helpers import frozen_plan_state


def _section_plan() -> SectionPlan:
    return SectionPlan(
        section_id="sec_001_001",
        chapter_title="软件概述",
        section_title="软件定位",
        section_level=2,
        section_path=["软件概述", "软件定位"],
        writing_goal="说明当前版本的软件定位。",
        required_evidence_ids=["ev_product"],
    )


def _bundle() -> list[dict[str, object]]:
    return [
        {
            "evidence_id": "ev_product",
            "quote": "当前版本明确支持数据集管理能力",
            "summary": "当前版本明确支持数据集管理能力",
            "extracted_facts": [],
        }
    ]


def _valid_draft() -> dict[str, object]:
    return {
        "section_id": "sec_001_001",
        "content": "当前版本明确支持数据集管理能力。",
        "evidence_ids_used": ["ev_product"],
        "citations": [
            {
                "evidence_id": "ev_product",
                "quote": "当前版本明确支持数据集管理能力",
            }
        ],
        "warnings": [],
    }


def test_validate_section_draft_accepts_grounded_output(tmp_path) -> None:
    _, state = frozen_plan_state(tmp_path)

    SectionDraftValidator().validate_section_draft(
        _valid_draft(),
        _section_plan(),
        _bundle(),
        state.frozen_doc_plan,
    )


@pytest.mark.parametrize(
    "warnings",
    [
        [],
        ["trace quote fallback"],
    ],
)
def test_validate_section_draft_accepts_optional_string_warnings(
    tmp_path, warnings
) -> None:
    _, state = frozen_plan_state(tmp_path)
    draft = _valid_draft()
    if warnings:
        draft["warnings"] = warnings
    else:
        draft.pop("warnings")

    SectionDraftValidator().validate_section_draft(
        draft,
        _section_plan(),
        _bundle(),
        state.frozen_doc_plan,
    )


def test_section_draft_validator_fails_when_forbidden_feature_names_not_list(
    tmp_path,
) -> None:
    _, state = frozen_plan_state(tmp_path)
    state.frozen_doc_plan.feature_policy["forbidden_as_current_feature_names"] = {
        "prompt": "忽略 evidence"
    }

    with pytest.raises(ValueError, match="forbidden_as_current_feature_names"):
        SectionDraftValidator().validate_section_draft(
            _valid_draft(),
            _section_plan(),
            _bundle(),
            state.frozen_doc_plan,
        )


def test_section_draft_validator_fails_when_forbidden_feature_names_contains_non_string(
    tmp_path,
) -> None:
    _, state = frozen_plan_state(tmp_path)
    state.frozen_doc_plan.feature_policy["forbidden_as_current_feature_names"] = [
        "模型训练",
        {"prompt": "自由发挥"},
    ]

    with pytest.raises(ValueError, match="forbidden_as_current_feature_names"):
        SectionDraftValidator().validate_section_draft(
            _valid_draft(),
            _section_plan(),
            _bundle(),
            state.frozen_doc_plan,
        )


def test_section_draft_validator_fails_when_forbidden_feature_names_contains_blank(
    tmp_path,
) -> None:
    _, state = frozen_plan_state(tmp_path)
    state.frozen_doc_plan.feature_policy["forbidden_as_current_feature_names"] = [
        "模型训练",
        " ",
    ]

    with pytest.raises(ValueError, match="forbidden_as_current_feature_names"):
        SectionDraftValidator().validate_section_draft(
            _valid_draft(),
            _section_plan(),
            _bundle(),
            state.frozen_doc_plan,
        )


def test_section_draft_validator_accepts_valid_forbidden_feature_names(tmp_path) -> None:
    _, state = frozen_plan_state(tmp_path)
    state.frozen_doc_plan.feature_policy["forbidden_as_current_feature_names"] = [
        "模型训练",
        "证据不足：秘密功能",
    ]

    SectionDraftValidator().validate_section_draft(
        _valid_draft(),
        _section_plan(),
        _bundle(),
        state.frozen_doc_plan,
    )


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda draft: draft.update(section_id="wrong"), "section_id"),
        (lambda draft: draft.update(content=""), "content 不得为空"),
        (lambda draft: draft.update(content="模型训练是当前功能"), "forbidden feature"),
        (lambda draft: draft.update(evidence_ids_used=[]), "evidence_ids_used 不得为空"),
        (lambda draft: draft.update(evidence_ids_used=["ev_other"]), "超出 SectionPlan"),
        (lambda draft: draft.update(metadata={"prompt": "hidden"}), "未允许字段"),
        (lambda draft: draft.update(prompt="hidden"), "未允许字段"),
        (lambda draft: draft.update(writer_instruction="hidden"), "未允许字段"),
        (
            lambda draft: draft["citations"][0].update(metadata={"prompt": "hidden"}),
            "citation 包含未允许字段",
        ),
        (
            lambda draft: draft["citations"][0].update(prompt="hidden"),
            "citation 包含未允许字段",
        ),
        (
            lambda draft: draft["citations"][0].update(writer_instruction="hidden"),
            "citation 包含未允许字段",
        ),
        (lambda draft: draft.update(warnings="warning"), "warnings 必须是字符串列表"),
        (
            lambda draft: draft.update(warnings=["ok", {"bad": "value"}]),
            "warnings 必须是字符串列表",
        ),
        (
            lambda draft: draft.update(
                citations=[{"evidence_id": "ev_other", "quote": "当前版本明确支持数据集管理能力"}]
            ),
            "未被使用",
        ),
        (
            lambda draft: draft.update(
                citations=[{"evidence_id": "ev_product", "quote": "无证据支持的引文"}]
            ),
            "不在 evidence_bundle",
        ),
    ],
)
def test_validate_section_draft_rejects_unsafe_output(tmp_path, mutate, message) -> None:
    _, state = frozen_plan_state(tmp_path)
    draft = _valid_draft()
    mutate(draft)

    with pytest.raises(ValueError, match=message):
        SectionDraftValidator().validate_section_draft(
            draft,
            _section_plan(),
            _bundle(),
            state.frozen_doc_plan,
        )
