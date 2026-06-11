from __future__ import annotations

import json
from pathlib import Path

import pytest
from docx import Document

from docforge_core.domain.enums import (
    EvidenceType,
    NextAction,
    ParseStatus,
    SourceType,
    WorkflowStatus,
)
from docforge_core.exporters.docx_exporter import docx_has_embedded_media
from docforge_core.io.file_registry import SourceFileRegistry
from docforge_core.io.run_paths import get_run_dir
from docforge_core.io.state_store import StateStore
from docforge_core.parsers.source_parsing_service import SourceParsingService
from docforge_core.workflow.e2e_sample_runner import default_e2e_sample_dir
from tests.helpers.e2e_workflow_helpers import (
    CURRENT_QUOTE,
    _confirm_minimal_chapters,
    _docx_text,
    _draft_sections,
    _load_json,
    _new_sample_run,
    _orchestrator,
    _run_sample_to_terminal,
    _sha256,
)


def test_upload_level_e2e_reaches_human_confirmation_before_freezing(
    tmp_path: Path,
) -> None:
    store, run_id = _new_sample_run(tmp_path)
    orchestrator = _orchestrator(store)

    summary = orchestrator.run_until_human_confirmation_required(run_id)

    state = store.load_state(run_id)
    assert summary.waiting_for_human_confirmation is True
    assert state.workflow_status == WorkflowStatus.USER_CONFIRM_REQUIRED
    assert state.next_action == NextAction.ASK_HUMAN_CONFIRMATION
    assert state.frozen_doc_plan is None
    _confirm_minimal_chapters(store, orchestrator, run_id)
    assert store.load_state(run_id).frozen_doc_plan is not None


def test_upload_level_e2e_sample_runs_to_docx(tmp_path: Path) -> None:
    store, run_id, docx_path = _run_sample_to_terminal(tmp_path)
    state = store.load_state(run_id)

    assert state.current_draft_version == "v1"
    assert (get_run_dir(run_id, store.data_dir) / "drafts" / "draft_v1.json").exists()
    assert (get_run_dir(run_id, store.data_dir) / "drafts" / "figure_slots_v1.json").exists()
    assert (get_run_dir(run_id, store.data_dir) / "drafts" / "audit_report_v1.json").exists()
    assert (get_run_dir(run_id, store.data_dir) / "drafts" / "quality_gate_report_v1.json").exists()
    assert Document(docx_path).paragraphs
    text = _docx_text(docx_path)
    assert "软件著作权文档" in text
    assert "墨衡演示数据管理平台" in text
    assert "V1.0" in text
    assert "核心功能说明" in text
    assert "此处建议插入" in text
    assert docx_has_embedded_media(docx_path) is False


def test_upload_level_e2e_validates_final_artifact_lineage(tmp_path: Path) -> None:
    store, run_id, docx_path = _run_sample_to_terminal(tmp_path)
    run_dir = get_run_dir(run_id, store.data_dir)
    draft_path = run_dir / "drafts" / "draft_v1.json"
    figure_path = run_dir / "drafts" / "figure_slots_v1.json"
    audit_path = run_dir / "drafts" / "audit_report_v1.json"
    gate_path = run_dir / "drafts" / "quality_gate_report_v1.json"
    manifest_path = run_dir / "exports" / "export_manifest.json"

    audit = _load_json(audit_path)
    gate = _load_json(gate_path)
    manifest = _load_json(manifest_path)
    assert audit["source_draft_hash"] == _sha256(draft_path)
    assert audit["source_figure_slots_hash"] == _sha256(figure_path)
    assert gate["source_audit_report_hash"] == _sha256(audit_path)
    assert gate["source_draft_hash"] == audit["source_draft_hash"]
    assert gate["source_figure_slots_hash"] == audit["source_figure_slots_hash"]
    assert manifest["output_docx_hash"] == _sha256(docx_path)
    assert manifest["source_quality_gate_report_hash"] == _sha256(gate_path)


def test_upload_level_e2e_final_docx_has_no_internal_artifacts(tmp_path: Path) -> None:
    _store, _run_id, docx_path = _run_sample_to_terminal(tmp_path)
    text = _docx_text(docx_path)

    for token in (
        "evidence_id",
        "source_id",
        "ev_",
        "finding_id",
        "export_manifest",
        "audit_report",
        "quality_gate_report",
        "source_draft_hash",
        CURRENT_QUOTE,
    ):
        assert token not in text


def test_upload_level_e2e_screenshot_is_registered_but_not_ocr(tmp_path: Path) -> None:
    store, run_id, _docx_path = _run_sample_to_terminal(tmp_path)
    state = store.load_state(run_id)
    screenshots = [
        item for item in state.evidence_map if item.evidence_type == EvidenceType.PRODUCT_SCREENSHOT
    ]

    assert len(screenshots) == 2
    assert all(item.screenshot_id for item in screenshots)
    assert all("OCR" in str(item.notes) or "视觉" in str(item.summary) for item in screenshots)
    assert all(item.content_ref and item.content_ref.endswith(".png") for item in screenshots)
    assert all(
        support.evidence_id not in {item.evidence_id for item in screenshots}
        for capability in state.product_capabilities
        for support in capability.evidence_supports
    )
    assert all(
        item.extracted_text_ref is None
        for item in state.parsed_assets
        if item.source_id in state.screenshot_source_ids
    )


def test_upload_level_e2e_screenshot_not_in_frozen_doc_plan_allowed_product_evidence(
    tmp_path: Path,
) -> None:
    store, run_id, _docx_path = _run_sample_to_terminal(tmp_path)
    state = store.load_state(run_id)
    assert state.frozen_doc_plan is not None
    screenshot_ids = {
        item.evidence_id
        for item in state.evidence_map
        if item.evidence_type == EvidenceType.PRODUCT_SCREENSHOT
    }
    policy = state.frozen_doc_plan.evidence_policy
    screenshot_policy = state.frozen_doc_plan.screenshot_policy

    assert screenshot_ids
    assert not screenshot_ids.intersection(policy["allowed_product_evidence_ids"])
    assert screenshot_ids.issubset(set(screenshot_policy["screenshot_evidence_ids"]))
    assert screenshot_policy["visual_parse_status"] == "not_performed"
    assert screenshot_policy["can_use_screenshot_as_strong_evidence"] is False
    assert screenshot_policy["can_use_screenshot_as_product_fact"] is False
    assert screenshot_policy["screenshot_usage"] == "figure_placeholder_only"
    assert screenshot_policy["screenshot_binding_status"] == "not_performed"
    assert all(
        support.evidence_id not in screenshot_ids
        for capability in state.product_capabilities
        for support in capability.evidence_supports
    )
    assert all(
        item["evidence_id"] not in screenshot_ids
        for item in policy["evidence_trace"]
    )
    assert all(
        not screenshot_ids.intersection(fact.get("supporting_evidence_ids", []))
        for fact in state.frozen_doc_plan.feature_policy["current_facts"]
    )


def test_upload_level_e2e_screenshot_not_in_section_required_evidence(
    tmp_path: Path,
) -> None:
    store, run_id, _docx_path = _run_sample_to_terminal(tmp_path)
    state = store.load_state(run_id)
    screenshot_ids = {
        item.evidence_id
        for item in state.evidence_map
        if item.evidence_type == EvidenceType.PRODUCT_SCREENSHOT
    }
    run_dir = get_run_dir(run_id, store.data_dir)
    draft_refs = [item.content_ref for item in state.draft_versions]

    assert screenshot_ids
    assert all(
        not screenshot_ids.intersection(section.required_evidence_ids)
        for section in state.section_plan
    )
    for draft_ref in draft_refs:
        draft = _load_json(run_dir / draft_ref)
        for section in _draft_sections(draft):
            assert not screenshot_ids.intersection(section.get("evidence_ids_used", []))
            citations = section.get("citations", [])
            assert all(citation.get("evidence_id") not in screenshot_ids for citation in citations)

    figure_slots = _load_json(run_dir / "drafts" / "figure_slots_v1.json")
    figure_text = json.dumps(figure_slots, ensure_ascii=False)
    assert "required_evidence_ids" not in figure_text
    assert all(
        "evidence_id" not in slot and "citations" not in slot
        for slot in figure_slots["figure_slots"]
    )
    assert all(slot["status"] == "missing" for slot in figure_slots["figure_slots"])


def test_upload_level_e2e_rejects_missing_product_evidence(tmp_path: Path) -> None:
    store = StateStore(data_dir=tmp_path)
    state = store.create_initial_state()
    fixture_dir = default_e2e_sample_dir()
    registry = SourceFileRegistry(state.run_id, data_dir=tmp_path)
    reference = registry.register_reference_file(
        "reference_soft_copyright.md",
        (fixture_dir / "reference_soft_copyright.md").read_bytes(),
    )
    store.add_source_item(state.run_id, reference)

    summary = _orchestrator(store).run_until_human_confirmation_required(state.run_id)

    reloaded = store.load_state(state.run_id)
    assert summary.success is False
    assert "product_evidence" in str(summary.error)
    assert reloaded.workflow_status == WorkflowStatus.EVIDENCE_MAPPED
    assert reloaded.template_strategy is None


def test_upload_level_e2e_rejects_missing_reference_style(tmp_path: Path) -> None:
    store = StateStore(data_dir=tmp_path)
    state = store.create_initial_state()
    fixture_dir = default_e2e_sample_dir()
    registry = SourceFileRegistry(state.run_id, data_dir=tmp_path)
    product = registry.register_product_file(
        "product_prd.md",
        (fixture_dir / "product_prd.md").read_bytes(),
        source_type=SourceType.PRD,
    )
    store.add_source_item(state.run_id, product)

    summary = _orchestrator(store).run_until_human_confirmation_required(state.run_id)

    reloaded = store.load_state(state.run_id)
    assert summary.success is False
    assert "reference_style" in str(summary.error)
    assert reloaded.workflow_status == WorkflowStatus.EVIDENCE_MAPPED
    assert reloaded.template_strategy is None


def test_upload_level_e2e_fails_closed_when_reference_used_as_product_evidence(
    tmp_path: Path,
) -> None:
    store = StateStore(data_dir=tmp_path)
    state = store.create_initial_state()
    fixture_dir = default_e2e_sample_dir()
    registry = SourceFileRegistry(state.run_id, data_dir=tmp_path)
    reference = registry.register_reference_file(
        "real_reference.md",
        (fixture_dir / "reference_soft_copyright.md").read_bytes(),
    )
    wrong_product = registry.register_product_file(
        "reference_misregistered.md",
        (fixture_dir / "reference_soft_copyright.md").read_bytes(),
        source_type=SourceType.PRD,
    )
    store.add_source_item(state.run_id, reference)
    store.add_source_item(state.run_id, wrong_product)

    summary = _orchestrator(store).run_until_human_confirmation_required(state.run_id)

    reloaded = store.load_state(state.run_id)
    assert summary.success is False
    assert "validated/current" in str(summary.error)
    assert reloaded.template_strategy is None
    assert reloaded.product_capabilities == []


def test_upload_level_e2e_resume_after_human_confirmation_pause(tmp_path: Path) -> None:
    store, run_id = _new_sample_run(tmp_path)
    first = _orchestrator(store)

    summary = first.run_until_human_confirmation_required(run_id)
    assert summary.waiting_for_human_confirmation is True
    paused = store.load_state(run_id)
    assert paused.workflow_status == WorkflowStatus.USER_CONFIRM_REQUIRED
    assert paused.frozen_doc_plan is None

    resumed = _orchestrator(store)
    _confirm_minimal_chapters(store, resumed, run_id)
    summary = resumed.run_until_terminal(run_id)
    assert summary.terminal is True
    final_state = store.load_state(run_id)
    assert final_state.workflow_status == WorkflowStatus.FINAL_EXPORTED


def test_upload_level_e2e_resume_after_audit_report_created(tmp_path: Path) -> None:
    store, run_id = _new_sample_run(tmp_path)
    orchestrator = _orchestrator(store)
    assert orchestrator.run_until_human_confirmation_required(run_id).waiting_for_human_confirmation
    _confirm_minimal_chapters(store, orchestrator, run_id)
    while store.load_state(run_id).workflow_status != WorkflowStatus.DRAFT_AUDITED:
        summary = orchestrator.run_next_step(run_id)
        assert summary.success is True

    audit_hash = _sha256(get_run_dir(run_id, store.data_dir) / "drafts" / "audit_report_v1.json")
    summary = _orchestrator(store).resume(run_id)

    assert summary.terminal is True
    assert _sha256(get_run_dir(run_id, store.data_dir) / "drafts" / "audit_report_v1.json") == audit_hash
    assert store.load_state(run_id).workflow_status == WorkflowStatus.FINAL_EXPORTED


def test_upload_level_e2e_repeated_continue_does_not_duplicate_artifacts(
    tmp_path: Path,
) -> None:
    store, run_id, _docx_path = _run_sample_to_terminal(tmp_path)
    state_before = store.load_state(run_id)
    run_dir = get_run_dir(run_id, store.data_dir)
    draft_files_before = sorted(path.name for path in (run_dir / "drafts").glob("draft_v*.json"))

    summary = _orchestrator(store).run_until_terminal(run_id)

    state_after = store.load_state(run_id)
    draft_files_after = sorted(path.name for path in (run_dir / "drafts").glob("draft_v*.json"))
    assert summary.terminal is True
    assert state_after.workflow_status == WorkflowStatus.FINAL_EXPORTED
    assert len(state_after.draft_versions) == len(state_before.draft_versions)
    assert draft_files_after == draft_files_before
    assert state_after.export_result == state_before.export_result


@pytest.mark.parametrize("source_name", ["login_page.png", "dashboard_page.png"])
def test_upload_level_sample_screenshot_sources_parse_without_text(
    tmp_path: Path,
    source_name: str,
) -> None:
    store, run_id = _new_sample_run(tmp_path)
    SourceParsingService(data_dir=tmp_path).parse_run(run_id)
    state = store.load_state(run_id)
    source = next(item for item in state.source_registry if item.file_name == source_name)
    asset = next(item for item in state.parsed_assets if item.source_id == source.source_id)

    assert source.parse_status == ParseStatus.PARSED
    assert asset.extracted_text_ref is None
    assert asset.image_ref is not None
