"""Create a validated document outline from a locked FrozenDocPlan."""

from __future__ import annotations

import json
from typing import Any

from docforge_core.domain.enums import LockedBy, LockedStatus, NextAction, WorkflowStatus
from docforge_core.domain.schemas import (
    DocForgeState,
    DocumentOutline,
    FrozenDocPlan,
    MissingInformationItem,
    SectionPlan,
)
from docforge_core.io.state_store import StateStore
from docforge_core.llm.base import LLMMessage, LLMProvider
from docforge_core.llm.prompt_loader import load_prompt

from ._shared import transition, unique_strings
from .outline_traversal import iter_outline_sections
from .outline_validator import OutlineValidator
from .section_plan_validator import SECTION_CONSTRAINTS
from .writing_plan_safety_items import collect_writing_plan_safety_items_from_outline
from .writing_plan_safety_verifier import (
    FAIL_CLOSED_REASON,
    WritingPlanSafetyVerifier,
    WritingPlanSafetyVerifierProtocol,
)


class OutlineAgent:
    """Expand locked top-level chapters without changing their contract."""

    def __init__(
        self,
        state_store: StateStore | None = None,
        llm_provider: LLMProvider | None = None,
        writing_plan_safety_verifier: WritingPlanSafetyVerifierProtocol | None = None,
    ) -> None:
        self.state_store = state_store or StateStore()
        self.llm_provider = llm_provider
        self.validator = OutlineValidator()
        self.writing_plan_safety_verifier = (
            writing_plan_safety_verifier
            or WritingPlanSafetyVerifier(llm_provider=self.llm_provider)
        )

    def create_outline(self, run_id: str) -> DocForgeState:
        state = self.state_store.load_state(run_id)
        plan = self._require_locked_plan(state)

        outline: DocumentOutline | None = None
        if self.llm_provider is not None:
            try:
                outline = self._build_llm_outline(state, plan)
                self.validator.validate_outline(outline, plan)
                self._validate_writing_plan_safety(outline)
            except Exception as exc:
                state.warnings.append(
                    f"OutlineAgent LLM outline 校验失败，已使用 deterministic fallback: {exc}"
                )
                outline = None
        if outline is None:
            outline = self._build_deterministic_outline(state)
            self.validator.validate_outline(outline, plan)
            self._validate_writing_plan_safety(outline)

        state.outline = outline
        state.section_plan = self._build_section_plan(outline)
        transition(
            state,
            WorkflowStatus.PLAN_FROZEN,
            WorkflowStatus.OUTLINE_CREATED,
            NextAction.RUN_PLAN_QUALITY_GATE,
            "OutlineAgent.create_outline",
            "document outline created from frozen plan",
        )
        self.state_store.save_state(state)
        return state

    def _validate_writing_plan_safety(self, outline: DocumentOutline) -> None:
        items = collect_writing_plan_safety_items_from_outline(outline)
        try:
            results = self.writing_plan_safety_verifier.verify_items(items)
        except Exception as exc:
            raise ValueError("WritingPlanSafetyVerifier 校验失败") from exc
        if len(results) != len(items):
            raise ValueError("WritingPlanSafetyVerifier 结果数量不完整")
        unsafe_results = [item for item in results if item.get("safe") is not True]
        if unsafe_results:
            if any(item.get("reason") == FAIL_CLOSED_REASON for item in unsafe_results):
                raise ValueError("WritingPlanSafetyVerifier fail closed")
            reason = str(unsafe_results[0].get("reason", "unsafe writing plan field"))
            raise ValueError(f"WritingPlanSafetyVerifier 发现不安全写作计划字段: {reason}")

    @staticmethod
    def _require_locked_plan(state: DocForgeState) -> FrozenDocPlan:
        if state.workflow_status != WorkflowStatus.PLAN_FROZEN:
            raise ValueError("创建 outline 要求 workflow_status 为 PLAN_FROZEN")
        plan = state.frozen_doc_plan
        if plan is None:
            raise ValueError("创建 outline 要求存在 frozen_doc_plan")
        if plan.locked_status != LockedStatus.LOCKED or plan.locked_by != LockedBy.HUMAN:
            raise ValueError("创建 outline 要求 FrozenDocPlan 已由 human 锁定")
        locked = plan.chapter_policy.get("locked_top_level_chapters", [])
        if not isinstance(locked, list) or not locked:
            raise ValueError("FrozenDocPlan 缺少 locked_top_level_chapters")
        if plan.downstream_permissions.get("outline_agent_can_change_top_level_chapters") is not False:
            raise ValueError("FrozenDocPlan 必须禁止 OutlineAgent 修改一级目录")
        return plan

    def _build_llm_outline(
        self,
        state: DocForgeState,
        plan: FrozenDocPlan,
    ) -> DocumentOutline:
        assert self.llm_provider is not None
        payload = {
            "locked_top_level_chapters": plan.chapter_policy.get(
                "locked_top_level_chapters", []
            ),
            "allowed_current_feature_names": plan.feature_policy.get(
                "allowed_current_feature_names", []
            ),
            "forbidden_as_current_feature_names": plan.feature_policy.get(
                "forbidden_as_current_feature_names", []
            ),
            "current_capabilities": plan.feature_policy.get("current_capabilities", []),
            "evidence_trace": plan.evidence_policy.get("evidence_trace", []),
            "writing_policy": plan.writing_policy,
            "risk_notes": plan.risk_notes,
        }
        raw = self.llm_provider.generate_json(
            [
                LLMMessage(role="system", content=load_prompt("outline.md")),
                LLMMessage(
                    role="user",
                    content=json.dumps(payload, ensure_ascii=False, indent=2),
                ),
            ]
        )
        chapters = raw.get("chapters")
        if not isinstance(chapters, list):
            raise ValueError("LLM outline 输出缺少 chapters 列表")
        return DocumentOutline(
            based_on_plan_id=plan.plan_id,
            chapters=chapters,
            required_evidence=plan.evidence_policy.get("evidence_trace", []),
            required_screenshots=plan.screenshot_policy.get(
                "screenshot_evidence_ids", []
            ),
        )

    def _build_deterministic_outline(self, state: DocForgeState) -> DocumentOutline:
        plan = state.frozen_doc_plan
        if plan is None:
            raise ValueError("deterministic outline 要求存在 frozen_doc_plan")
        locked_titles = plan.chapter_policy["locked_top_level_chapters"]
        capabilities = plan.feature_policy.get("current_capabilities", [])
        facts = plan.feature_policy.get("current_facts", [])
        evidence_trace = plan.evidence_policy.get("evidence_trace", [])
        allowed_current_names = plan.feature_policy.get(
            "allowed_current_feature_names", []
        )
        chapters: list[dict[str, Any]] = []

        for chapter_index, title in enumerate(locked_titles, start=1):
            sections = self._deterministic_sections(
                str(title),
                chapter_index,
                capabilities,
                facts,
                evidence_trace,
                allowed_current_names,
            )
            chapters.append(
                {
                    "chapter_id": f"ch_{chapter_index:03d}",
                    "level": 1,
                    "title": title,
                    "source": "frozen_doc_plan.chapter_policy.locked_top_level_chapters",
                    "locked": True,
                    "sections": sections,
                }
            )
            for section in sections:
                if section.get("needs_human_confirmation"):
                    question = f"请补充“{title} / {section['title']}”所需的产品证据。"
                    if question not in state.pending_human_questions:
                        state.pending_human_questions.append(question)
                    if not any(
                        item.question == question for item in state.missing_information
                    ):
                        state.missing_information.append(
                            MissingInformationItem(
                                question=question,
                                reason="OutlineAgent 未找到该章节可绑定的 product_evidence",
                                related_chapter=str(title),
                                related_feature=str(section["title"]),
                            )
                        )

        return DocumentOutline(
            based_on_plan_id=plan.plan_id,
            chapters=chapters,
            required_evidence=evidence_trace,
            required_screenshots=plan.screenshot_policy.get(
                "screenshot_evidence_ids", []
            ),
        )

    def _deterministic_sections(
        self,
        chapter_title: str,
        chapter_index: int,
        capabilities: list[dict[str, Any]],
        facts: list[dict[str, Any]],
        evidence_trace: list[dict[str, Any]],
        allowed_current_names: list[str],
    ) -> list[dict[str, Any]]:
        all_evidence = unique_strings(
            [str(item.get("evidence_id", "")) for item in evidence_trace]
        )
        all_capability_ids = [
            str(item.get("capability_id", "")) for item in capabilities if item.get("capability_id")
        ]
        all_fact_ids = [str(item.get("fact_id", "")) for item in facts if item.get("fact_id")]

        if "核心功能" in chapter_title:
            capability_by_name = {
                str(item.get("name", "")): item for item in capabilities
            }
            sections: list[dict[str, Any]] = []
            for section_index, feature_name in enumerate(
                allowed_current_names, start=1
            ):
                capability = capability_by_name.get(str(feature_name))
                if capability is None:
                    sections.append(
                        self._section(
                            chapter_index,
                            section_index,
                            str(feature_name),
                            f"等待补充{feature_name}的产品证据。",
                            [],
                            [],
                            [],
                            needs_human_confirmation=True,
                        )
                    )
                else:
                    sections.append(
                        self._capability_section(
                            chapter_index,
                            section_index,
                            capability,
                            facts,
                            evidence_trace,
                            writing_goal=(
                                f"说明{capability.get('name')}的当前版本能力和使用范围。"
                            ),
                        )
                    )
            return sections or [self._placeholder_section(chapter_index, 1)]
        if "用户操作流程" in chapter_title:
            return [
                self._capability_section(
                    chapter_index,
                    section_index,
                    capability,
                    facts,
                    evidence_trace,
                    writing_goal=f"说明{capability.get('name')}的用户操作流程、关键步骤和操作结果。",
                )
                for section_index, capability in enumerate(capabilities, start=1)
            ] or [self._placeholder_section(chapter_index, 1)]
        if "软件概述" in chapter_title:
            return [
                self._section(
                    chapter_index,
                    1,
                    "软件定位",
                    "说明软件定位、适用场景和目标用户。",
                    all_evidence,
                    all_capability_ids,
                    all_fact_ids,
                ),
                self._section(
                    chapter_index,
                    2,
                    "主要功能概述",
                    "概述当前版本的主要产品能力。",
                    all_evidence,
                    all_capability_ids,
                    all_fact_ids,
                ),
            ]
        if "运行环境" in chapter_title:
            return [
                self._section(
                    chapter_index,
                    1,
                    "硬件环境",
                    "等待补充硬件环境证据。",
                    [],
                    [],
                    [],
                    needs_human_confirmation=True,
                ),
                self._section(
                    chapter_index,
                    2,
                    "软件环境",
                    "等待补充软件环境证据。",
                    [],
                    [],
                    [],
                    needs_human_confirmation=True,
                ),
            ]
        if "登录" in chapter_title or "首页" in chapter_title:
            supported = [
                item
                for item in capabilities
                if "登录" in str(item.get("name", "")) or "首页" in str(item.get("name", ""))
            ]
            if supported:
                return [
                    self._capability_section(
                        chapter_index,
                        index,
                        item,
                        facts,
                        evidence_trace,
                        writing_goal=f"说明{item.get('name')}。",
                    )
                    for index, item in enumerate(supported, start=1)
                ]
            return [
                self._section(
                    chapter_index,
                    1,
                    "登录入口" if "登录" in chapter_title else "首页功能概览",
                    "等待补充对应产品证据。",
                    [],
                    [],
                    [],
                    needs_human_confirmation=True,
                )
            ]
        return [
            self._section(
                chapter_index,
                1,
                "章节说明",
                "说明本章节涉及的当前产品事实和主要内容。",
                all_evidence,
                all_capability_ids,
                all_fact_ids,
                needs_human_confirmation=not all_evidence,
            )
        ]

    def _capability_section(
        self,
        chapter_index: int,
        section_index: int,
        capability: dict[str, Any],
        facts: list[dict[str, Any]],
        evidence_trace: list[dict[str, Any]],
        writing_goal: str,
    ) -> dict[str, Any]:
        capability_id = str(capability.get("capability_id", ""))
        evidence_ids = unique_strings(
            [
                str(item.get("evidence_id", ""))
                for item in evidence_trace
                if item.get("capability_id") == capability_id
            ]
        )
        fact_ids = [
            str(item["fact_id"])
            for item in facts
            if item.get("fact_id") == f"fact_{capability_id}"
        ]
        return self._section(
            chapter_index,
            section_index,
            str(capability.get("name", "能力说明")),
            writing_goal,
            evidence_ids,
            [capability_id],
            fact_ids,
            needs_human_confirmation=not evidence_ids,
        )

    @staticmethod
    def _section(
        chapter_index: int,
        section_index: int,
        title: str,
        writing_goal: str,
        evidence_ids: list[str],
        capability_ids: list[str],
        fact_ids: list[str],
        needs_human_confirmation: bool = False,
    ) -> dict[str, Any]:
        return {
            "section_id": f"sec_{chapter_index:03d}_{section_index:03d}",
            "level": 2,
            "title": title,
            "writing_goal": writing_goal,
            "required_evidence_ids": evidence_ids,
            "required_capability_ids": capability_ids,
            "required_fact_ids": fact_ids,
            "needs_human_confirmation": needs_human_confirmation,
        }

    def _placeholder_section(self, chapter_index: int, section_index: int) -> dict[str, Any]:
        return self._section(
            chapter_index,
            section_index,
            "章节说明",
            "等待补充本章节所需的产品证据和写作目标。",
            [],
            [],
            [],
            needs_human_confirmation=True,
        )

    @staticmethod
    def _build_section_plan(outline: DocumentOutline) -> list[SectionPlan]:
        return [
            SectionPlan(
                section_id=str(node.section["section_id"]),
                chapter_title=node.chapter_title,
                section_title=str(node.section["title"]),
                section_level=node.section_level,
                parent_section_title=node.parent_section_title,
                section_path=node.section_path,
                writing_goal=str(node.section.get("writing_goal", "")),
                required_evidence_ids=list(
                    node.section.get("required_evidence_ids", [])
                ),
                required_capability_ids=list(
                    node.section.get("required_capability_ids", [])
                ),
                required_fact_ids=list(node.section.get("required_fact_ids", [])),
                needs_human_confirmation=bool(
                    node.section.get("needs_human_confirmation", False)
                ),
                required_screenshot_ids=[],
                writing_constraints=list(SECTION_CONSTRAINTS),
            )
            for node in iter_outline_sections(outline)
        ]
