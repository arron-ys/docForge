"""Validate that SectionPlan is an untampered safe projection of an outline."""

from docforge_core.domain.schemas import DocumentOutline, SectionPlan

from .outline_traversal import OutlineSectionNode, iter_outline_sections
from .title_injection_safety import validate_outline_title_safe
from .writing_goal_safety import validate_writing_goal_safe

SECTION_CONSTRAINTS = [
    "必须使用 product_evidence 作为产品事实",
    "不得使用 reference_style 作为产品事实",
    "不得将 planned / unknown 写成当前功能",
    "不得修改 FrozenDocPlan 锁定的一级目录",
]


class SectionPlanValidator:
    """Protect the future WriterAgent from a drifting or weakened plan."""

    def validate_section_plan_matches_outline(
        self,
        outline: DocumentOutline,
        section_plan: list[SectionPlan],
    ) -> None:
        for item in section_plan:
            self._validate_plan_titles(item)

        outline_nodes = iter_outline_sections(outline)
        expected = {self._node_key(node): node for node in outline_nodes}
        planned = {self._plan_key(item): item for item in section_plan}
        if (
            len(expected) != len(outline_nodes)
            or len(planned) != len(section_plan)
            or expected.keys() != planned.keys()
        ):
            raise ValueError("section_plan 与 outline 不一致")

        for key, node in expected.items():
            item = planned[key]
            section = node.section
            if item.writing_goal != str(section.get("writing_goal", "")):
                raise ValueError("section_plan writing_goal 被篡改")
            validate_writing_goal_safe(item.writing_goal)
            if item.required_evidence_ids != self._strings(
                section.get("required_evidence_ids")
            ):
                raise ValueError("section_plan 与 outline 不一致")
            if item.required_capability_ids != self._strings(
                section.get("required_capability_ids")
            ):
                raise ValueError("section_plan 与 outline 不一致")
            if item.required_fact_ids != self._strings(section.get("required_fact_ids")):
                raise ValueError("section_plan 与 outline 不一致")
            if item.needs_human_confirmation is not bool(
                section.get("needs_human_confirmation", False)
            ):
                raise ValueError("section_plan 与 outline 不一致")
            self._validate_writing_constraints(item.writing_constraints)

    @staticmethod
    def _validate_plan_titles(item: SectionPlan) -> None:
        try:
            validate_outline_title_safe(item.section_title)
        except ValueError as exc:
            raise ValueError(
                "section_plan section_title 包含不安全写作指令"
            ) from exc
        for title in item.section_path:
            try:
                validate_outline_title_safe(title)
            except ValueError as exc:
                raise ValueError(
                    "section_plan section_path 包含不安全写作指令"
                ) from exc
        if item.parent_section_title is not None:
            try:
                validate_outline_title_safe(item.parent_section_title)
            except ValueError as exc:
                raise ValueError(
                    "section_plan parent_section_title 包含不安全写作指令"
                ) from exc

    @staticmethod
    def _node_key(node: OutlineSectionNode) -> tuple[object, ...]:
        return (
            str(node.section.get("section_id", "")),
            node.chapter_title,
            str(node.section.get("title", "")),
            node.section_level,
            tuple(node.section_path),
            node.parent_section_title,
        )

    @staticmethod
    def _plan_key(item: SectionPlan) -> tuple[object, ...]:
        return (
            item.section_id,
            item.chapter_title,
            item.section_title,
            item.section_level,
            tuple(item.section_path),
            item.parent_section_title,
        )

    @staticmethod
    def _strings(value: object) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(item) for item in value if item]

    @classmethod
    def _validate_writing_constraints(cls, constraints: list[str]) -> None:
        if not constraints:
            raise ValueError("section_plan 缺少安全写作约束")
        normalized_actual = [cls._normalize_constraint(item) for item in constraints]
        if any(not item for item in normalized_actual):
            raise ValueError("section_plan writing_constraints 包含空约束")
        if len(normalized_actual) != len(set(normalized_actual)):
            raise ValueError("section_plan writing_constraints 包含重复约束")
        normalized_expected = {
            cls._normalize_constraint(item) for item in SECTION_CONSTRAINTS
        }
        if set(normalized_actual) != normalized_expected:
            raise ValueError("section_plan writing_constraints 必须严格等于系统安全约束")

    @staticmethod
    def _normalize_constraint(value: str) -> str:
        return "".join(value.strip().lower().split())
