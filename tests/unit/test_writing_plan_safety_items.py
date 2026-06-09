from docforge_core.agents.outline_agent import OutlineAgent
from docforge_core.agents.writing_plan_safety_items import (
    collect_writing_plan_safety_items_from_outline,
    collect_writing_plan_safety_items_from_section_plan,
)
from docforge_core.domain.schemas import DocumentOutline


def _outline() -> DocumentOutline:
    return DocumentOutline(
        based_on_plan_id="plan",
        chapters=[
            {
                "chapter_id": "ch_1",
                "level": 1,
                "title": "软件概述",
                "locked": True,
                "sections": [
                    {
                        "section_id": "sec_1",
                        "level": 2,
                        "title": "软件定位",
                        "writing_goal": "说明软件定位。",
                        "required_evidence_ids": ["ev_product"],
                        "sections": [
                            {
                                "section_id": "sec_1_1",
                                "level": 3,
                                "title": "定位详情",
                                "writing_goal": "说明定位详情。",
                                "required_evidence_ids": ["ev_product"],
                            }
                        ],
                    }
                ],
            }
        ],
    )


def test_collect_from_outline_includes_level_2_title_and_writing_goal() -> None:
    items = collect_writing_plan_safety_items_from_outline(_outline())

    assert {
        (item["field_kind"], item["text"])
        for item in items
    } >= {
        ("section_title", "软件定位"),
        ("writing_goal", "说明软件定位。"),
    }


def test_collect_from_outline_includes_level_3_title_and_writing_goal() -> None:
    items = collect_writing_plan_safety_items_from_outline(_outline())

    assert {
        (item["field_kind"], item["text"])
        for item in items
    } >= {
        ("section_title", "定位详情"),
        ("writing_goal", "说明定位详情。"),
    }


def test_collect_from_section_plan_includes_title_and_writing_goal() -> None:
    plans = OutlineAgent._build_section_plan(_outline())
    items = collect_writing_plan_safety_items_from_section_plan(plans)

    assert {
        (item["field_kind"], item["text"])
        for item in items
    } >= {
        ("section_title", "软件定位"),
        ("writing_goal", "说明软件定位。"),
    }


def test_collect_from_section_plan_includes_parent_section_title() -> None:
    plans = OutlineAgent._build_section_plan(_outline())
    items = collect_writing_plan_safety_items_from_section_plan(plans)

    assert ("parent_section_title", "软件定位") in {
        (item["field_kind"], item["text"])
        for item in items
    }


def test_collect_from_section_plan_includes_each_section_path_item() -> None:
    plans = OutlineAgent._build_section_plan(_outline())
    items = collect_writing_plan_safety_items_from_section_plan(plans)

    path_items = [
        item["text"]
        for item in items
        if item["field_kind"] == "section_path_item"
    ]
    assert "软件概述" in path_items
    assert "软件定位" in path_items
    assert "定位详情" in path_items


def test_collect_from_section_plan_does_not_collect_constraints_or_quotes() -> None:
    plans = OutlineAgent._build_section_plan(_outline())
    items = collect_writing_plan_safety_items_from_section_plan(plans)
    texts = [item["text"] for item in items]

    assert all("不得使用 reference_style 作为产品事实" not in text for text in texts)
    assert all("quote" not in item for item in items)
