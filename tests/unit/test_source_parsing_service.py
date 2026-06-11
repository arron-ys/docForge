from pathlib import Path

import pytest
from pypdf import PdfWriter

from docforge_core.domain.enums import (
    AllowedUsage,
    AssetType,
    CorpusType,
    FileType,
    NextAction,
    ParseStatus,
    SourceType,
    WorkflowStatus,
)
from docforge_core.domain.schemas import SourceItem
from docforge_core.io.file_registry import SourceFileRegistry
from docforge_core.io.state_store import StateStore
from docforge_core.parsers.source_parsing_service import SourceParsingService


@pytest.fixture()
def store(tmp_path: Path) -> StateStore:
    return StateStore(data_dir=tmp_path)


def test_parse_run_parses_uploaded_txt_product_material(
    tmp_path: Path, store: StateStore
) -> None:
    state = store.create_initial_state()
    registry = SourceFileRegistry(state.run_id, data_dir=tmp_path)
    source_item = registry.register_product_file("prd.txt", "产品功能\n\n流程".encode(), SourceType.PRD)
    store.add_source_item(state.run_id, source_item)

    parsed_state = SourceParsingService(data_dir=tmp_path).parse_run(state.run_id)

    assert parsed_state.source_registry[0].parse_status == ParseStatus.PARSED
    assert parsed_state.parsed_assets
    assert parsed_state.parsed_assets[0].asset_type == AssetType.TEXT


def test_parse_run_resolves_api_relative_source_path(
    tmp_path: Path, store: StateStore
) -> None:
    state = store.create_initial_state()
    source_path = tmp_path / "runs" / state.run_id / "sources" / "product" / "prd.txt"
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_text("产品能力\n\n业务流程", encoding="utf-8")
    source_item = SourceItem(
        source_type=SourceType.PRD,
        file_type=FileType.TXT,
        corpus_type=CorpusType.PRODUCT_EVIDENCE,
        allowed_usage=AllowedUsage.FACTUAL_EVIDENCE,
        file_name="prd.txt",
        file_path="sources/product/prd.txt",
        is_product_source=True,
        parse_status=ParseStatus.PENDING,
    )
    store.add_source_item(state.run_id, source_item)

    parsed_state = SourceParsingService(data_dir=tmp_path).parse_run(state.run_id)

    assert parsed_state.source_registry[0].parse_status == ParseStatus.PARSED
    assert parsed_state.parsed_assets[0].extracted_text_ref == (
        f"parsed/{source_item.source_id}/chunk_001.txt"
    )


def test_parse_run_resolves_legacy_run_relative_source_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    data_dir = Path("data")
    store = StateStore(data_dir=data_dir)
    state = store.create_initial_state()
    source_path = data_dir / "runs" / state.run_id / "sources" / "product" / "legacy.txt"
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_text("遗留路径资料", encoding="utf-8")
    source_item = SourceItem(
        source_type=SourceType.PRD,
        file_type=FileType.TXT,
        corpus_type=CorpusType.PRODUCT_EVIDENCE,
        allowed_usage=AllowedUsage.FACTUAL_EVIDENCE,
        file_name="legacy.txt",
        file_path=str(source_path),
        is_product_source=True,
        parse_status=ParseStatus.PENDING,
    )
    store.add_source_item(state.run_id, source_item)

    parsed_state = SourceParsingService(data_dir=data_dir).parse_run(state.run_id)

    assert parsed_state.source_registry[0].parse_status == ParseStatus.PARSED
    assert parsed_state.parsed_assets


def test_parse_run_parses_uploaded_md_reference_material(
    tmp_path: Path, store: StateStore
) -> None:
    state = store.create_initial_state()
    registry = SourceFileRegistry(state.run_id, data_dir=tmp_path)
    source_item = registry.register_reference_file("reference.md", "# 目录\n\n章节写法".encode())
    store.add_source_item(state.run_id, source_item)

    parsed_state = SourceParsingService(data_dir=tmp_path).parse_run(state.run_id)

    assert parsed_state.source_registry[0].parse_status == ParseStatus.PARSED
    assert parsed_state.parsed_assets[0].source_id == source_item.source_id


def test_parse_run_registers_uploaded_screenshot(tmp_path: Path, store: StateStore) -> None:
    state = store.create_initial_state()
    registry = SourceFileRegistry(state.run_id, data_dir=tmp_path)
    source_item = registry.register_screenshot_file("screen.png", b"fake-image")
    store.add_source_item(state.run_id, source_item)

    parsed_state = SourceParsingService(data_dir=tmp_path).parse_run(state.run_id)

    asset = parsed_state.parsed_assets[0]
    assert parsed_state.source_registry[0].parse_status == ParseStatus.PARSED
    assert asset.asset_type == AssetType.SCREENSHOT
    assert asset.image_ref is not None


def test_parse_run_records_failed_status_and_error(tmp_path: Path, store: StateStore) -> None:
    state = store.create_initial_state()
    source_item = SourceItem(
        source_id="missing_source",
        source_type=SourceType.PRD,
        file_type=FileType.TXT,
        corpus_type=CorpusType.PRODUCT_EVIDENCE,
        allowed_usage=AllowedUsage.FACTUAL_EVIDENCE,
        file_name="missing.txt",
        file_path=str(tmp_path / "missing.txt"),
        is_product_source=True,
    )
    store.add_source_item(state.run_id, source_item)

    parsed_state = SourceParsingService(data_dir=tmp_path).parse_run(state.run_id)

    assert parsed_state.source_registry[0].parse_status == ParseStatus.FAILED
    assert parsed_state.source_registry[0].parse_error


def test_parse_run_bad_pdf_marks_source_failed(tmp_path: Path, store: StateStore) -> None:
    state = store.create_initial_state()
    registry = SourceFileRegistry(state.run_id, data_dir=tmp_path)
    source_item = registry.register_product_file("bad.pdf", b"not a pdf", SourceType.PRD)
    store.add_source_item(state.run_id, source_item)

    parsed_state = SourceParsingService(data_dir=tmp_path).parse_run(state.run_id)

    assert parsed_state.source_registry[0].parse_status == ParseStatus.FAILED
    assert parsed_state.source_registry[0].parse_error
    assert parsed_state.parsed_assets == []


def test_parse_run_valid_pdf_without_text_does_not_fail(
    tmp_path: Path, store: StateStore
) -> None:
    state = store.create_initial_state()
    registry = SourceFileRegistry(state.run_id, data_dir=tmp_path)
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    pdf_path = tmp_path / "blank.pdf"
    with pdf_path.open("wb") as file:
        writer.write(file)
    source_item = registry.register_product_file("blank.pdf", pdf_path.read_bytes(), SourceType.PRD)
    store.add_source_item(state.run_id, source_item)

    parsed_state = SourceParsingService(data_dir=tmp_path).parse_run(state.run_id)

    assert parsed_state.source_registry[0].parse_status == ParseStatus.PARSED
    assert parsed_state.parsed_assets == []


def test_parse_run_writes_chunk_files_and_relative_text_refs(
    tmp_path: Path, store: StateStore
) -> None:
    state = store.create_initial_state()
    registry = SourceFileRegistry(state.run_id, data_dir=tmp_path)
    source_item = registry.register_product_file("prd.txt", b"chunk one\n\nchunk two", SourceType.PRD)
    store.add_source_item(state.run_id, source_item)

    parsed_state = SourceParsingService(data_dir=tmp_path).parse_run(state.run_id)

    refs = [asset.extracted_text_ref for asset in parsed_state.parsed_assets]
    assert refs == [
        f"parsed/{source_item.source_id}/chunk_001.txt",
        f"parsed/{source_item.source_id}/chunk_002.txt",
    ]
    for ref in refs:
        assert (tmp_path / "runs" / state.run_id / str(ref)).exists()


def test_parse_run_image_ref_is_relative_to_run_dir(tmp_path: Path, store: StateStore) -> None:
    state = store.create_initial_state()
    registry = SourceFileRegistry(state.run_id, data_dir=tmp_path)
    source_item = registry.register_screenshot_file("screen.webp", b"fake-image")
    store.add_source_item(state.run_id, source_item)

    parsed_state = SourceParsingService(data_dir=tmp_path).parse_run(state.run_id)

    assert parsed_state.parsed_assets[0].image_ref == "sources/screenshots/screen.webp"


def test_parse_run_transitions_to_source_parsed(tmp_path: Path, store: StateStore) -> None:
    state = store.create_initial_state()
    registry = SourceFileRegistry(state.run_id, data_dir=tmp_path)
    source_item = registry.register_product_file("prd.txt", b"content", SourceType.PRD)
    uploaded_state = store.add_source_item(state.run_id, source_item)

    parsed_state = SourceParsingService(data_dir=tmp_path).parse_run(state.run_id)

    assert uploaded_state.workflow_status == WorkflowStatus.MATERIAL_UPLOADED
    assert parsed_state.workflow_status == WorkflowStatus.SOURCE_PARSED
    assert parsed_state.next_action == NextAction.ANALYZE_REFERENCE_STYLE
    assert parsed_state.status_history[-1].node_name == "SourceParsingService.parse_run"
    assert parsed_state.status_history[-1].reason == "source materials parsed"


def test_parse_run_all_failed_does_not_enter_source_parsed(
    tmp_path: Path, store: StateStore
) -> None:
    state = store.create_initial_state()
    source_item = SourceItem(
        source_id="missing_source",
        source_type=SourceType.PRD,
        file_type=FileType.TXT,
        corpus_type=CorpusType.PRODUCT_EVIDENCE,
        allowed_usage=AllowedUsage.FACTUAL_EVIDENCE,
        file_name="missing.txt",
        file_path=str(tmp_path / "missing.txt"),
        is_product_source=True,
    )
    store.add_source_item(state.run_id, source_item)

    parsed_state = SourceParsingService(data_dir=tmp_path).parse_run(state.run_id)

    assert parsed_state.workflow_status == WorkflowStatus.MATERIAL_UPLOADED
    assert parsed_state.next_action == NextAction.PARSE_SOURCES
    assert parsed_state.parsed_assets == []


def test_parse_run_keeps_product_url_source_ids_empty(tmp_path: Path, store: StateStore) -> None:
    state = store.create_initial_state()
    registry = SourceFileRegistry(state.run_id, data_dir=tmp_path)
    source_item = registry.register_product_file("prd.txt", b"content", SourceType.PRD)
    store.add_source_item(state.run_id, source_item)

    parsed_state = SourceParsingService(data_dir=tmp_path).parse_run(state.run_id)

    assert parsed_state.product_url_source_ids == []
