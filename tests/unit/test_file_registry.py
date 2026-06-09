from pathlib import Path

import pytest

from docforge_core.domain.enums import (
    AllowedUsage,
    CorpusType,
    FileType,
    ParseStatus,
    SourceType,
)
from docforge_core.io.file_registry import SourceFileRegistry


@pytest.fixture()
def registry(tmp_path: Path) -> SourceFileRegistry:
    return SourceFileRegistry(run_id="run_test", data_dir=tmp_path)


def test_register_reference_file_saves_to_reference_dir(registry: SourceFileRegistry) -> None:
    item = registry.register_reference_file("参考软著.docx", b"content")

    assert Path(item.file_path or "").read_bytes() == b"content"
    assert Path(item.file_path or "").parent.name == "reference"


def test_register_reference_file_creates_reference_source_item(
    registry: SourceFileRegistry,
) -> None:
    item = registry.register_reference_file("reference.pdf", b"content")

    assert item.source_type == SourceType.REFERENCE_SOFT_COPYRIGHT_DOC
    assert item.corpus_type == CorpusType.REFERENCE_STYLE
    assert item.allowed_usage == AllowedUsage.STYLE_ONLY
    assert item.is_reference_source is True
    assert item.is_product_source is False
    assert item.parse_status == ParseStatus.PENDING


def test_register_reference_file_does_not_accept_source_type(
    registry: SourceFileRegistry,
) -> None:
    register_reference_file = getattr(registry, "register_reference_file")

    with pytest.raises(TypeError):
        register_reference_file("reference.docx", b"content", SourceType.PRD)


def test_register_product_file_saves_to_product_dir(registry: SourceFileRegistry) -> None:
    item = registry.register_product_file("prd.md", b"content", SourceType.PRD)

    assert Path(item.file_path or "").read_bytes() == b"content"
    assert Path(item.file_path or "").parent.name == "product"


def test_register_product_file_creates_product_source_item(
    registry: SourceFileRegistry,
) -> None:
    item = registry.register_product_file("hld.html", b"content", SourceType.HLD)

    assert item.source_type == SourceType.HLD
    assert item.corpus_type == CorpusType.PRODUCT_EVIDENCE
    assert item.allowed_usage == AllowedUsage.FACTUAL_EVIDENCE
    assert item.is_reference_source is False
    assert item.is_product_source is True
    assert item.parse_status == ParseStatus.PENDING


def test_register_screenshot_file_saves_to_screenshots_dir(
    registry: SourceFileRegistry,
) -> None:
    item = registry.register_screenshot_file("page.png", b"content")

    assert Path(item.file_path or "").read_bytes() == b"content"
    assert Path(item.file_path or "").parent.name == "screenshots"


def test_register_screenshot_file_creates_screenshot_source_item(
    registry: SourceFileRegistry,
) -> None:
    item = registry.register_screenshot_file("page.webp", b"content")

    assert item.source_type == SourceType.SCREENSHOT
    assert item.file_type == FileType.WEBP
    assert item.corpus_type == CorpusType.PRODUCT_EVIDENCE
    assert item.allowed_usage == AllowedUsage.DISPLAY_MATERIAL_ONLY
    assert item.is_reference_source is False
    assert item.is_product_source is True
    assert item.parse_status == ParseStatus.PENDING


def test_same_file_name_does_not_overwrite(registry: SourceFileRegistry) -> None:
    first = registry.register_product_file("prd.txt", b"first", SourceType.PRD)
    second = registry.register_product_file("prd.txt", b"second", SourceType.PRD)

    assert first.file_path != second.file_path
    assert Path(first.file_path or "").read_bytes() == b"first"
    assert Path(second.file_path or "").read_bytes() == b"second"


def test_path_traversal_file_name_stays_inside_target_dir(
    registry: SourceFileRegistry,
) -> None:
    item = registry.register_reference_file("../../escape.txt", b"content")
    saved_path = Path(item.file_path or "").resolve()
    reference_dir = (
        registry.data_dir / "runs" / registry.run_id / "sources" / "reference"
        if registry.data_dir is not None
        else Path()
    ).resolve()

    assert saved_path.parent == reference_dir
    assert item.file_name == "escape.txt"


def test_unsupported_extension_raises_value_error(registry: SourceFileRegistry) -> None:
    with pytest.raises(ValueError, match="不支持"):
        registry.register_reference_file("bad.exe", b"content")


def test_file_type_is_detected_from_extension(registry: SourceFileRegistry) -> None:
    assert registry.register_reference_file("a.docx", b"x").file_type == FileType.DOCX
    assert registry.register_reference_file("a.pdf", b"x").file_type == FileType.PDF
    assert registry.register_reference_file("a.md", b"x").file_type == FileType.MD
    assert registry.register_reference_file("a.txt", b"x").file_type == FileType.TXT
    assert registry.register_product_file("a.html", b"x", SourceType.OTHER).file_type == FileType.HTML
    assert registry.register_screenshot_file("a.png", b"x").file_type == FileType.PNG
    assert registry.register_screenshot_file("a.jpg", b"x").file_type == FileType.JPG
    assert registry.register_screenshot_file("a.jpeg", b"x").file_type == FileType.JPEG
    assert registry.register_screenshot_file("a.webp", b"x").file_type == FileType.WEBP
