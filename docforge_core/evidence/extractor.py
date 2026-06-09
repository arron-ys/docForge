"""Deterministic EvidenceItem extraction from ParsedAsset records."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from docforge_core.domain.enums import (
    AllowedUsage,
    CorpusType,
    EvidenceStrength,
    EvidenceType,
    NextAction,
    SourceType,
    WorkflowStatus,
)
from docforge_core.domain.schemas import (
    DocForgeState,
    EvidenceItem,
    ParsedAsset,
    SourceItem,
    StateTransitionLog,
)
from docforge_core.io.run_paths import get_evidence_dir
from docforge_core.io.state_store import StateStore

REFERENCE_NOTES = (
    "该证据只允许用于目录结构、章节写法、配图方式、语言风格，"
    "不允许作为产品事实来源。"
)
SCREENSHOT_FALLBACK_SUMMARY = "产品截图已登记，视觉解析将在后续 Sprint 实现。"
PRODUCT_DOCUMENT_TYPES = {
    SourceType.PRODUCT_INTRO_DOC,
    SourceType.PRD,
    SourceType.HLD,
    SourceType.DETAILED_DESIGN_DOC,
    SourceType.OTHER,
}
TAG_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("data_platform", ("数据集", "数据资产", "样本", "标注", "质检", "导入", "导出")),
    ("ai_platform", ("模型", "训练", "推理", "评测", "lora", "微调")),
    ("web_saas", ("登录", "首页", "页面", "按钮", "菜单", "列表")),
    ("permission", ("权限", "角色", "用户管理")),
)


class EvidenceExtractorService:
    """Build and persist a run-scoped, isolated evidence map."""

    def __init__(self, data_dir: Path | None = None) -> None:
        self.data_dir = data_dir
        self.state_store = StateStore(data_dir=data_dir)

    def extract_run(self, run_id: str) -> DocForgeState:
        state = self.state_store.load_state(run_id)
        if state.workflow_status in {WorkflowStatus.CREATED, WorkflowStatus.MATERIAL_UPLOADED}:
            raise ValueError("Evidence 抽取要求 workflow_status 至少为 SOURCE_PARSED")

        sources = {item.source_id: item for item in state.source_registry}
        evidence_by_id = {item.evidence_id: item for item in state.evidence_map}

        for asset in state.parsed_assets:
            source = sources.get(asset.source_id)
            if source is None:
                raise ValueError(f"ParsedAsset 找不到对应 SourceItem: {asset.source_id}")
            evidence = self._to_evidence(source, asset)
            if evidence is not None:
                evidence_by_id[evidence.evidence_id] = evidence

        state.evidence_map = list(evidence_by_id.values())
        self._write_evidence_map(state)

        if state.evidence_map and state.workflow_status == WorkflowStatus.SOURCE_PARSED:
            state.status_history.append(
                StateTransitionLog(
                    from_status=WorkflowStatus.SOURCE_PARSED,
                    to_status=WorkflowStatus.EVIDENCE_MAPPED,
                    node_name="EvidenceExtractorService.extract_run",
                    reason="evidence units extracted",
                )
            )
            state.workflow_status = WorkflowStatus.EVIDENCE_MAPPED
            state.next_action = NextAction.DIAGNOSE_SOFTWARE_TYPE

        self.state_store.save_state(state)
        return state

    def _write_evidence_map(self, state: DocForgeState) -> Path:
        target = get_evidence_dir(state.run_id, self.data_dir) / "evidence_map.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = [item.model_dump(mode="json") for item in state.evidence_map]
        target.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return target

    def _to_evidence(self, source: SourceItem, asset: ParsedAsset) -> EvidenceItem | None:
        if source.source_type == SourceType.PRODUCT_URL:
            return None

        common: dict[str, Any] = {
            "evidence_id": f"ev_{source.source_id}_{asset.asset_id}",
            "source_id": source.source_id,
            "source_type": source.source_type,
            "file_type": source.file_type,
            "corpus_type": source.corpus_type,
            "allowed_usage": source.allowed_usage,
            "function_name": None,
            "related_module": None,
            "related_chapter": None,
            "content_ref": asset.extracted_text_ref or asset.image_ref,
            "source_location": (
                f"page:{asset.page_number}"
                if asset.page_number is not None
                else f"asset:{asset.asset_id}"
            ),
            "location": asset.extracted_text_ref or asset.image_ref,
            "metadata": {
                "asset_id": asset.asset_id,
                "asset_type": asset.asset_type.value,
            },
        }

        if source.corpus_type == CorpusType.REFERENCE_STYLE:
            return EvidenceItem(
                **common,
                evidence_type=EvidenceType.REFERENCE_STYLE_ONLY,
                evidence_strength=EvidenceStrength.NOT_ALLOWED_AS_FACT,
                summary=asset.summary,
                extracted_facts=[],
                tags=["reference_style"],
                confidence=1.0,
                is_confirmed=False,
                needs_human_confirmation=False,
                notes=REFERENCE_NOTES,
            )

        if source.source_type == SourceType.SCREENSHOT:
            screenshot_common = {
                **common,
                "allowed_usage": AllowedUsage.DISPLAY_MATERIAL_ONLY,
            }
            return EvidenceItem(
                **screenshot_common,
                evidence_type=EvidenceType.PRODUCT_SCREENSHOT,
                evidence_strength=EvidenceStrength.NOT_ALLOWED_AS_FACT,
                summary=asset.summary or SCREENSHOT_FALLBACK_SUMMARY,
                extracted_facts=[],
                tags=["screenshot"],
                screenshot_id=source.source_id,
                confidence=1.0,
                is_confirmed=False,
                needs_human_confirmation=False,
                notes="仅登记截图，不做 OCR 或视觉内容推断，不作为产品事实证据。",
            )

        if source.source_type == SourceType.USER_NOTE:
            return EvidenceItem(
                **common,
                evidence_type=EvidenceType.USER_CONFIRMATION,
                evidence_strength=EvidenceStrength.WEAK,
                summary=asset.summary,
                extracted_facts=self._raw_summary_fact(asset.summary, 0.6),
                tags=["user_note"],
                confidence=0.6,
                is_confirmed=False,
                needs_human_confirmation=True,
                notes="用户补充说明默认作为弱证据，需人工确认。",
            )

        if source.source_type in PRODUCT_DOCUMENT_TYPES:
            summary = asset.summary or ""
            return EvidenceItem(
                **common,
                evidence_type=EvidenceType.PRODUCT_DOCUMENT,
                evidence_strength=EvidenceStrength.MEDIUM,
                summary=asset.summary,
                extracted_facts=self._raw_summary_fact(asset.summary, 0.6),
                tags=self._product_document_tags(summary),
                confidence=0.8,
                is_confirmed=False,
                needs_human_confirmation=False,
                notes="Sprint 5 使用规则化摘要证据，不调用 LLM 做复杂事实抽取。",
            )

        return None

    @staticmethod
    def _raw_summary_fact(summary: str | None, confidence: float) -> list[dict[str, Any]]:
        if not summary:
            return []
        return [
            {
                "fact_type": "raw_text_summary",
                "content": summary,
                "confidence": confidence,
            }
        ]

    @staticmethod
    def _product_document_tags(summary: str) -> list[str]:
        normalized = summary.lower()
        tags = [
            tag
            for tag, keywords in TAG_KEYWORDS
            if any(keyword.lower() in normalized for keyword in keywords)
        ]
        return tags or ["product_document"]
