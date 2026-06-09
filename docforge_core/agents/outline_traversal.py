"""Shared recursive traversal for level-2 and level-3 outline sections."""

from dataclasses import dataclass
from typing import Any

from docforge_core.domain.schemas import DocumentOutline


@dataclass(frozen=True)
class OutlineSectionNode:
    """A section plus its stable location under a top-level chapter."""

    chapter_title: str
    section: dict[str, Any]
    section_level: int
    section_path: list[str]
    parent_section_title: str | None


def iter_outline_sections(outline: DocumentOutline) -> list[OutlineSectionNode]:
    """Return every nested section while preserving outline order."""

    result: list[OutlineSectionNode] = []

    def append_sections(
        chapter_title: str,
        sections: Any,
        parent_path: list[str],
        parent_section_title: str | None,
    ) -> None:
        if not isinstance(sections, list):
            return
        for section in sections:
            if not isinstance(section, dict):
                continue
            title = str(section.get("title", ""))
            path = [*parent_path, title]
            raw_level = section.get("level", 0)
            section_level = raw_level if isinstance(raw_level, int) else 0
            result.append(
                OutlineSectionNode(
                    chapter_title=chapter_title,
                    section=section,
                    section_level=section_level,
                    section_path=path,
                    parent_section_title=parent_section_title,
                )
            )
            append_sections(
                chapter_title,
                section.get("sections", []),
                path,
                title,
            )

    for chapter in outline.chapters:
        chapter_title = str(chapter.get("title", ""))
        append_sections(
            chapter_title,
            chapter.get("sections", []),
            [chapter_title],
            None,
        )
    return result
