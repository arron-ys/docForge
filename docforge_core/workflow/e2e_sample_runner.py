"""Local E2E sample-project source registration helpers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from docforge_core.domain.enums import SourceType
from docforge_core.domain.schemas import SourceItem
from docforge_core.io.file_registry import SourceFileRegistry
from docforge_core.io.state_store import StateStore

SAMPLE_FIXTURE_NAME = "e2e_sample"
SAMPLE_SOURCE_FILE_NAMES = (
    "reference_soft_copyright.md",
    "product_prd.md",
    "product_hld.md",
    "product_intro.md",
    "screenshots/login_page.png",
    "screenshots/dashboard_page.png",
)
EXPECTED_SAMPLE_FIXTURE_PATHS = frozenset(SAMPLE_SOURCE_FILE_NAMES)


@dataclass(frozen=True, slots=True)
class E2ESampleImportResult:
    """Result of registering the local sample project into a run."""

    run_id: str
    source_items: tuple[SourceItem, ...]
    imported_count: int
    skipped_existing: bool = False


def default_e2e_sample_dir() -> Path:
    """Return the repo-local sample fixture directory."""
    return Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "e2e_sample"


def load_e2e_sample_project(
    store: StateStore,
    run_id: str,
    sample_dir: Path | None = None,
) -> E2ESampleImportResult:
    """Register the repo-local E2E sample files through SourceFileRegistry."""
    fixture_dir = sample_dir or default_e2e_sample_dir()
    _validate_fixture_dir(fixture_dir)

    state = store.load_state(run_id)
    existing = [
        item
        for item in state.source_registry
        if item.metadata.get("sample_fixture") == SAMPLE_FIXTURE_NAME
    ]
    if existing:
        _validate_existing_sample_sources(existing)
        return E2ESampleImportResult(
            run_id=run_id,
            source_items=tuple(existing),
            imported_count=0,
            skipped_existing=True,
        )

    registry = SourceFileRegistry(run_id, data_dir=store.data_dir)
    created: list[SourceItem] = []
    created.append(
        _mark_sample_source(
            registry.register_reference_file(
                "reference_soft_copyright.md",
                (fixture_dir / "reference_soft_copyright.md").read_bytes(),
            ),
            "reference_soft_copyright.md",
        )
    )
    for file_name, source_type in (
        ("product_prd.md", SourceType.PRD),
        ("product_hld.md", SourceType.HLD),
        ("product_intro.md", SourceType.PRODUCT_INTRO_DOC),
    ):
        created.append(
            _mark_sample_source(
                registry.register_product_file(
                    file_name,
                    (fixture_dir / file_name).read_bytes(),
                    source_type=source_type,
                ),
                file_name,
            )
        )
    for file_name in ("login_page.png", "dashboard_page.png"):
        created.append(
            _mark_sample_source(
                registry.register_screenshot_file(
                    file_name,
                    (fixture_dir / "screenshots" / file_name).read_bytes(),
                ),
                f"screenshots/{file_name}",
            )
        )
    for source_item in created:
        store.add_source_item(run_id, source_item)
    _apply_sample_run_metadata(store, run_id)

    return E2ESampleImportResult(
        run_id=run_id,
        source_items=tuple(created),
        imported_count=len(created),
    )


def _validate_fixture_dir(sample_dir: Path) -> None:
    missing = [
        str(sample_dir / relative_path)
        for relative_path in SAMPLE_SOURCE_FILE_NAMES
        if not (sample_dir / relative_path).is_file()
    ]
    readme = sample_dir / "README.md"
    if not readme.is_file():
        missing.append(str(readme))
    if missing:
        raise FileNotFoundError("样例工程 fixture 缺失: " + ", ".join(missing))


def _validate_existing_sample_sources(existing: list[SourceItem]) -> None:
    fixture_paths: set[str] = set()
    for source_item in existing:
        fixture_path = source_item.metadata.get("fixture_path")
        if not isinstance(fixture_path, str) or not fixture_path.strip():
            raise ValueError("样例工程处于不完整或异常导入状态")
        fixture_paths.add(fixture_path)

    if len(fixture_paths) != len(existing):
        raise ValueError("样例工程处于不完整或异常导入状态，存在重复 fixture_path")

    unknown = fixture_paths - EXPECTED_SAMPLE_FIXTURE_PATHS
    if unknown:
        raise ValueError(
            "样例工程处于不完整或异常导入状态，存在未知 fixture_path: "
            + ", ".join(sorted(unknown))
        )
    missing = EXPECTED_SAMPLE_FIXTURE_PATHS - fixture_paths
    if missing:
        raise ValueError(
            "样例工程处于部分导入状态，缺少 fixture_path: "
            + ", ".join(sorted(missing))
        )


def _mark_sample_source(source_item: SourceItem, fixture_path: str) -> SourceItem:
    source_item.metadata["sample_fixture"] = SAMPLE_FIXTURE_NAME
    source_item.metadata["fixture_path"] = fixture_path
    return source_item


def _apply_sample_run_metadata(store: StateStore, run_id: str) -> None:
    state = store.load_state(run_id)
    state.project_name = state.project_name or "Sprint15 样例工程"
    state.target_product_name = "墨衡演示数据管理平台"
    state.output_requirements["version"] = "V1.0"
    state.output_requirements["software_version"] = "V1.0"
    state.output_requirements["output_format"] = "docx"
    state.output_requirements["export_pdf"] = False
    state.output_requirements["export_markdown"] = False
    store.save_state(state)
