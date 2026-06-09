import json
from pathlib import Path

import pytest

from docforge_core.domain.enums import (
    AllowedUsage,
    AssetType,
    CorpusType,
    EvidenceStrength,
    EvidenceType,
    FileType,
    NextAction,
    SourceType,
    WorkflowStatus,
)
from docforge_core.domain.schemas import ParsedAsset, SourceItem
from docforge_core.evidence.extractor import EvidenceExtractorService
from docforge_core.io.run_paths import get_evidence_dir
from docforge_core.io.state_store import StateStore


def _source(
    source_id: str,
    source_type: SourceType,
    corpus_type: CorpusType,
) -> SourceItem:
    is_reference = corpus_type == CorpusType.REFERENCE_STYLE
    is_screenshot = source_type == SourceType.SCREENSHOT
    return SourceItem(
        source_id=source_id,
        source_type=source_type,
        file_type=FileType.PNG if source_type == SourceType.SCREENSHOT else FileType.TXT,
        corpus_type=corpus_type,
        allowed_usage=(
            AllowedUsage.STYLE_ONLY
            if is_reference
            else (
                AllowedUsage.DISPLAY_MATERIAL_ONLY
                if is_screenshot
                else AllowedUsage.FACTUAL_EVIDENCE
            )
        ),
        file_name=f"{source_id}.txt",
        file_path=f"/tmp/{source_id}.txt",
        is_reference_source=is_reference,
        is_product_source=not is_reference,
    )


def _asset(source_id: str, asset_id: str, summary: str = "产品首页支持数据集导入") -> ParsedAsset:
    return ParsedAsset(
        asset_id=asset_id,
        source_id=source_id,
        asset_type=AssetType.TEXT,
        summary=summary,
        extracted_text_ref=f"parsed/{source_id}/chunk.txt",
    )


def _prepare_run(
    tmp_path: Path,
    pairs: list[tuple[SourceItem, ParsedAsset]],
) -> tuple[StateStore, str]:
    store = StateStore(data_dir=tmp_path)
    state = store.create_initial_state()
    state.source_registry = [source for source, _ in pairs]
    state.parsed_assets = [asset for _, asset in pairs]
    state.workflow_status = WorkflowStatus.SOURCE_PARSED
    state.next_action = NextAction.ANALYZE_REFERENCE_STYLE
    store.save_state(state)
    return store, state.run_id


def test_reference_style_generates_isolated_evidence(tmp_path: Path) -> None:
    source = _source("ref", SourceType.REFERENCE_SOFT_COPYRIGHT_DOC, CorpusType.REFERENCE_STYLE)
    store, run_id = _prepare_run(tmp_path, [(source, _asset("ref", "a1", "章节写法"))])

    state = EvidenceExtractorService(data_dir=tmp_path).extract_run(run_id)
    evidence = state.evidence_map[0]

    assert evidence.evidence_type == EvidenceType.REFERENCE_STYLE_ONLY
    assert evidence.allowed_usage == AllowedUsage.STYLE_ONLY
    assert evidence.evidence_strength == EvidenceStrength.NOT_ALLOWED_AS_FACT
    assert evidence.extracted_facts == []
    assert evidence.tags == ["reference_style"]
    assert store.load_state(run_id).evidence_map == state.evidence_map


def test_product_document_generates_factual_medium_evidence(tmp_path: Path) -> None:
    source = _source("prd", SourceType.PRD, CorpusType.PRODUCT_EVIDENCE)
    _, run_id = _prepare_run(tmp_path, [(source, _asset("prd", "a1"))])

    evidence = EvidenceExtractorService(data_dir=tmp_path).extract_run(run_id).evidence_map[0]

    assert evidence.evidence_type == EvidenceType.PRODUCT_DOCUMENT
    assert evidence.allowed_usage == AllowedUsage.FACTUAL_EVIDENCE
    assert evidence.evidence_strength == EvidenceStrength.MEDIUM
    assert {"data_platform", "web_saas"} <= set(evidence.tags)
    assert evidence.extracted_facts[0]["fact_type"] == "raw_text_summary"


def test_screenshot_generates_display_material_without_visual_inference(tmp_path: Path) -> None:
    source = _source("screen", SourceType.SCREENSHOT, CorpusType.PRODUCT_EVIDENCE)
    asset = ParsedAsset(
        asset_id="image1",
        source_id="screen",
        asset_type=AssetType.SCREENSHOT,
        summary="",
        image_ref="sources/screenshots/screen.png",
    )
    _, run_id = _prepare_run(tmp_path, [(source, asset)])

    evidence = EvidenceExtractorService(data_dir=tmp_path).extract_run(run_id).evidence_map[0]

    assert evidence.evidence_type == EvidenceType.PRODUCT_SCREENSHOT
    assert evidence.allowed_usage == AllowedUsage.DISPLAY_MATERIAL_ONLY
    assert evidence.evidence_strength == EvidenceStrength.NOT_ALLOWED_AS_FACT
    assert evidence.extracted_facts == []
    assert evidence.tags == ["screenshot"]
    assert evidence.screenshot_id == source.source_id
    assert "视觉解析将在后续 Sprint 实现" in str(evidence.summary)
    assert "不作为产品事实证据" in str(evidence.notes)


def test_user_note_generates_weak_confirmation_evidence(tmp_path: Path) -> None:
    source = _source("note", SourceType.USER_NOTE, CorpusType.PRODUCT_EVIDENCE)
    _, run_id = _prepare_run(tmp_path, [(source, _asset("note", "a1", "用户补充说明"))])

    evidence = EvidenceExtractorService(data_dir=tmp_path).extract_run(run_id).evidence_map[0]

    assert evidence.evidence_type == EvidenceType.USER_CONFIRMATION
    assert evidence.evidence_strength == EvidenceStrength.WEAK
    assert evidence.needs_human_confirmation is True


def test_product_url_does_not_generate_evidence(tmp_path: Path) -> None:
    source = _source("url", SourceType.PRODUCT_URL, CorpusType.PRODUCT_EVIDENCE)
    _, run_id = _prepare_run(tmp_path, [(source, _asset("url", "a1"))])

    state = EvidenceExtractorService(data_dir=tmp_path).extract_run(run_id)

    assert state.evidence_map == []
    assert state.workflow_status == WorkflowStatus.SOURCE_PARSED


def test_extract_run_persists_map_is_idempotent_and_transitions(tmp_path: Path) -> None:
    source = _source("prd", SourceType.PRD, CorpusType.PRODUCT_EVIDENCE)
    store, run_id = _prepare_run(tmp_path, [(source, _asset("prd", "a1"))])
    extractor = EvidenceExtractorService(data_dir=tmp_path)

    first = extractor.extract_run(run_id)
    second = extractor.extract_run(run_id)

    assert len(second.evidence_map) == 1
    assert second.workflow_status == WorkflowStatus.EVIDENCE_MAPPED
    assert second.next_action == NextAction.DIAGNOSE_SOFTWARE_TYPE
    transitions = [
        item
        for item in second.status_history
        if item.node_name == "EvidenceExtractorService.extract_run"
    ]
    assert len(transitions) == 1
    assert transitions[0].reason == "evidence units extracted"
    evidence_file = get_evidence_dir(run_id, tmp_path) / "evidence_map.json"
    assert evidence_file.exists()
    assert json.loads(evidence_file.read_text(encoding="utf-8"))[0]["evidence_id"] == (
        first.evidence_map[0].evidence_id
    )
    assert store.load_state(run_id).evidence_map == second.evidence_map


def test_extract_run_requires_source_parsed_status(tmp_path: Path) -> None:
    store = StateStore(data_dir=tmp_path)
    state = store.create_initial_state()

    with pytest.raises(ValueError, match="SOURCE_PARSED"):
        EvidenceExtractorService(data_dir=tmp_path).extract_run(state.run_id)
