"""Strong validation for outlines derived from FrozenDocPlan."""

from typing import Any

from docforge_core.domain.schemas import DocumentOutline, FrozenDocPlan

from .section_evidence_policy import assess_section_evidence
from .title_injection_safety import validate_outline_title_safe
from .title_safety import is_forbidden_title
from .writing_goal_safety import validate_writing_goal_safe

BODY_FIELDS = {
    "paragraph",
    "paragraphs",
    "body",
    "bodies",
    "content",
    "contents",
    "text",
    "texts",
    "draft",
    "draft_text",
    "draft_content",
    "section_text",
    "section_content",
    "generated_text",
    "generated_content",
    "markdown",
    "md",
    "html",
    "正文",
    "正文内容",
    "段落",
    "段落内容",
}
ALLOWED_CHAPTER_FIELDS = {
    "chapter_id",
    "level",
    "title",
    "source",
    "locked",
    "sections",
}
ALLOWED_SECTION_FIELDS = {
    "section_id",
    "level",
    "title",
    "writing_goal",
    "required_evidence_ids",
    "required_capability_ids",
    "required_fact_ids",
    "needs_human_confirmation",
    "sections",
}


class OutlineValidator:
    def validate_outline(
        self,
        outline: DocumentOutline,
        frozen_doc_plan: FrozenDocPlan,
    ) -> None:
        if outline.based_on_plan_id != frozen_doc_plan.plan_id:
            raise ValueError("outline based_on_plan_id 必须指向当前 FrozenDocPlan")
        locked_titles = frozen_doc_plan.chapter_policy.get(
            "locked_top_level_chapters", []
        )
        chapter_titles = [chapter.get("title") for chapter in outline.chapters]
        if chapter_titles != locked_titles:
            raise ValueError("outline 一级章节必须与 locked_top_level_chapters 完全一致")

        forbidden = frozen_doc_plan.feature_policy.get(
            "forbidden_as_current_feature_names", []
        )
        product_ids = set(
            frozen_doc_plan.evidence_policy.get("allowed_product_evidence_ids", [])
        )
        reference_ids = set(
            frozen_doc_plan.evidence_policy.get("allowed_reference_style_ids", [])
        )
        capability_ids = {
            item.get("capability_id")
            for item in frozen_doc_plan.feature_policy.get("current_capabilities", [])
        }
        fact_ids = {
            item.get("fact_id")
            for item in frozen_doc_plan.feature_policy.get("current_facts", [])
        }
        seen_section_ids: set[str] = set()

        for chapter in outline.chapters:
            if not isinstance(chapter, dict):
                raise ValueError("outline chapters 必须为对象")
            self._reject_body_fields(chapter)
            self._reject_unknown_fields(chapter, ALLOWED_CHAPTER_FIELDS)
            if chapter.get("level") != 1 or chapter.get("locked") is not True:
                raise ValueError("outline 一级章节必须 level=1 且 locked=true")
            sections = chapter.get("sections", [])
            if not isinstance(sections, list):
                raise ValueError("outline chapter.sections 必须为列表")
            for section in sections:
                self._validate_section(
                    section,
                    expected_level=2,
                    forbidden=forbidden,
                    product_ids=product_ids,
                    reference_ids=reference_ids,
                    capability_ids=capability_ids,
                    fact_ids=fact_ids,
                    frozen_doc_plan=frozen_doc_plan,
                    seen_section_ids=seen_section_ids,
                )

    def _validate_section(
        self,
        section: Any,
        *,
        expected_level: int,
        forbidden: list[str],
        product_ids: set[str],
        reference_ids: set[str],
        capability_ids: set[Any],
        fact_ids: set[Any],
        frozen_doc_plan: FrozenDocPlan,
        seen_section_ids: set[str],
    ) -> None:
        if not isinstance(section, dict):
            raise ValueError("outline sections 必须为对象")
        self._reject_body_fields(section)
        self._reject_unknown_fields(section, ALLOWED_SECTION_FIELDS)
        if section.get("level") != expected_level:
            raise ValueError(f"outline section level 必须为 {expected_level}")
        section_id = str(section.get("section_id", "")).strip()
        title = str(section.get("title", "")).strip()
        writing_goal = str(section.get("writing_goal", "")).strip()
        if not section_id:
            raise ValueError("outline section_id 不得为空")
        if section_id in seen_section_ids:
            raise ValueError("outline section_id 必须唯一")
        seen_section_ids.add(section_id)
        if not title:
            raise ValueError("outline section title 不得为空")
        validate_outline_title_safe(title)
        if not writing_goal:
            raise ValueError("outline section writing_goal 不得为空")
        validate_writing_goal_safe(writing_goal)
        if is_forbidden_title(title, forbidden):
            raise ValueError("outline section 不得包含 forbidden feature 或其变体")
        if is_forbidden_title(writing_goal, forbidden):
            raise ValueError(
                "outline section writing_goal 不得包含 forbidden feature 或其变体"
            )
        evidence_ids = set(section.get("required_evidence_ids", []))
        if evidence_ids.intersection(reference_ids):
            raise ValueError("outline 不得使用 reference_style evidence")
        if not evidence_ids.issubset(product_ids):
            raise ValueError("outline required_evidence_ids 包含未知 product evidence")
        if not set(section.get("required_capability_ids", [])).issubset(capability_ids):
            raise ValueError("outline required_capability_ids 包含未知 capability")
        if not set(section.get("required_fact_ids", [])).issubset(fact_ids):
            raise ValueError("outline required_fact_ids 包含未知 fact")
        assessment = assess_section_evidence(section, frozen_doc_plan)
        if assessment.is_capability_related and not evidence_ids:
            raise ValueError("能力相关章节必须绑定对应 product_evidence")
        elif (
            assessment.expected_evidence_ids
            and not assessment.expected_evidence_ids.issubset(evidence_ids)
        ):
            raise ValueError("能力相关章节必须绑定对应 product_evidence")
        if (
            assessment.unresolved_capability_ids
            or assessment.unresolved_fact_ids
            or assessment.unresolved_title_match
        ):
            raise ValueError("能力相关章节必须绑定对应 product_evidence")

        child_sections = section.get("sections", [])
        if not isinstance(child_sections, list):
            raise ValueError("outline section.sections 必须为列表")
        if expected_level == 3 and child_sections:
            raise ValueError("outline 不支持超过三级的章节")
        for child in child_sections:
            self._validate_section(
                child,
                expected_level=3,
                forbidden=forbidden,
                product_ids=product_ids,
                reference_ids=reference_ids,
                capability_ids=capability_ids,
                fact_ids=fact_ids,
                frozen_doc_plan=frozen_doc_plan,
                seen_section_ids=seen_section_ids,
            )

    @staticmethod
    def _reject_body_fields(value: dict[str, Any]) -> None:
        normalized_keys = {
            key.strip().lower() for key in value if isinstance(key, str)
        }
        if BODY_FIELDS.intersection(normalized_keys):
            raise ValueError("outline 不得包含正文内容字段")

    @staticmethod
    def _reject_unknown_fields(
        value: dict[str, Any],
        allowed_fields: set[str],
    ) -> None:
        normalized_keys = {
            key.strip() for key in value if isinstance(key, str)
        }
        if len(normalized_keys) != len(value) or not normalized_keys.issubset(
            allowed_fields
        ):
            raise ValueError("outline 包含未允许字段")
