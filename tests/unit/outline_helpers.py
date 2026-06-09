from pathlib import Path

from docforge_core.domain.enums import LockedBy, LockedStatus, WorkflowStatus
from docforge_core.domain.schemas import FrozenDocPlan

from .agent_helpers import save_state


class SafeWritingPlanSafetyVerifier:
    def verify_items(self, items):
        return [
            {
                "item_index": item["item_index"],
                "safe": True,
                "risk_type": "none",
                "reason": "test safe verifier",
            }
            for item in items
        ]


def frozen_plan_state(tmp_path: Path):
    store, state = save_state(tmp_path, WorkflowStatus.PLAN_FROZEN)
    state.target_product_name = "墨衡测试软件"
    state.output_requirements["version"] = "V1.0"
    state.frozen_doc_plan = FrozenDocPlan(
        project_id=state.project_id,
        locked_status=LockedStatus.LOCKED,
        locked_by=LockedBy.HUMAN,
        software_identity={
            "target_product_name": "墨衡测试软件",
            "version": "V1.0",
        },
        diagnosis_snapshot={"primary_type": "Web/SaaS 平台"},
        template_decision={"base_template_id": "TEMPLATE_WEB"},
        chapter_policy={
            "locked_top_level_chapters": ["软件概述", "核心功能说明"],
            "optional_chapters": [],
            "risk_chapters": [],
            "excluded_chapters": [],
            "can_outline_add_level_2_sections": True,
            "can_outline_change_level_1_sections": False,
            "requires_reconfirmation_to_change_level_1": True,
        },
        feature_policy={
            "current_capabilities": [
                {
                    "capability_id": "cap_current",
                    "name": "数据集管理",
                    "evidence_supports": [
                        {
                            "evidence_id": "ev_product",
                            "source_id": "product_source",
                            "quote": "当前版本明确支持数据集管理能力",
                        }
                    ],
                }
            ],
            "current_facts": [
                {
                    "fact_id": "fact_cap_current",
                    "content": "数据集管理",
                }
            ],
            "planned_capabilities": [{"capability_id": "cap_planned", "name": "模型训练"}],
            "unknown_capabilities": [],
            "unsupported_or_rejected_features": ["证据不足：秘密功能"],
            "allowed_current_feature_names": ["数据集管理"],
            "forbidden_as_current_feature_names": ["模型训练", "证据不足：秘密功能"],
        },
        evidence_policy={
            "factual_evidence_filter": {
                "corpus_type": "product_evidence",
                "allowed_usage": "factual_evidence",
            },
            "style_reference_filter": {
                "corpus_type": "reference_style",
                "allowed_usage": "style_only",
            },
            "allowed_product_evidence_ids": ["ev_product"],
            "allowed_reference_style_ids": ["ev_reference"],
            "evidence_trace": [
                {
                    "capability_id": "cap_current",
                    "capability_name": "数据集管理",
                    "evidence_id": "ev_product",
                    "source_id": "product_source",
                    "quote": "当前版本明确支持数据集管理能力",
                    "corpus_type": "product_evidence",
                    "allowed_usage": "factual_evidence",
                }
            ],
        },
        screenshot_policy={"screenshot_evidence_ids": []},
        writing_policy={},
        downstream_permissions={"outline_agent_can_change_top_level_chapters": False},
    )
    store.save_state(state)
    return store, state
