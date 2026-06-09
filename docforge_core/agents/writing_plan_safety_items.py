"""Collect compact writing-plan fields for semantic safety verification."""

from typing import Any

from docforge_core.domain.schemas import DocumentOutline, SectionPlan

from .outline_traversal import iter_outline_sections


def collect_writing_plan_safety_items_from_outline(
    outline: DocumentOutline,
) -> list[dict[str, Any]]:
    """Collect section titles and writing goals from an outline."""

    items: list[dict[str, Any]] = []
    for node in iter_outline_sections(outline):
        section_id = str(node.section.get("section_id", ""))
        title = str(node.section.get("title", ""))
        writing_goal = str(node.section.get("writing_goal", ""))
        _append_item(
            items,
            field_kind="section_title",
            text=title,
            section_id=section_id,
            chapter_title=node.chapter_title,
            section_path=node.section_path,
            context={"section_level": node.section_level},
        )
        _append_item(
            items,
            field_kind="writing_goal",
            text=writing_goal,
            section_id=section_id,
            chapter_title=node.chapter_title,
            section_path=node.section_path,
            context={"section_level": node.section_level},
        )
    return items


def collect_writing_plan_safety_items_from_section_plan(
    section_plan: list[SectionPlan],
) -> list[dict[str, Any]]:
    """Collect mutable Writer-facing fields from SectionPlan."""

    items: list[dict[str, Any]] = []
    for plan in section_plan:
        _append_item(
            items,
            field_kind="section_title",
            text=plan.section_title,
            section_id=plan.section_id,
            chapter_title=plan.chapter_title,
            section_path=plan.section_path,
            context={"section_level": plan.section_level},
        )
        _append_item(
            items,
            field_kind="writing_goal",
            text=plan.writing_goal,
            section_id=plan.section_id,
            chapter_title=plan.chapter_title,
            section_path=plan.section_path,
            context={"section_level": plan.section_level},
        )
        if plan.parent_section_title is not None:
            _append_item(
                items,
                field_kind="parent_section_title",
                text=plan.parent_section_title,
                section_id=plan.section_id,
                chapter_title=plan.chapter_title,
                section_path=plan.section_path,
                context={"section_level": plan.section_level},
            )
        for path_item in plan.section_path:
            _append_item(
                items,
                field_kind="section_path_item",
                text=path_item,
                section_id=plan.section_id,
                chapter_title=plan.chapter_title,
                section_path=plan.section_path,
                context={"section_level": plan.section_level},
            )
    return items


def _append_item(
    items: list[dict[str, Any]],
    *,
    field_kind: str,
    text: str,
    section_id: str | None,
    chapter_title: str | None,
    section_path: list[str],
    context: dict[str, Any] | None,
) -> None:
    items.append(
        {
            "item_index": len(items),
            "field_kind": field_kind,
            "text": text,
            "section_id": section_id,
            "chapter_title": chapter_title,
            "section_path": list(section_path),
            "context": context or {},
        }
    )
