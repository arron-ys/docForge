from pathlib import Path

import pytest

from docforge_core.domain.enums import (
    AllowedUsage,
    CorpusType,
    FileType,
    ParseStatus,
    SourceType,
)
from docforge_core.domain.schemas import SourceItem
from docforge_core.io.state_store import StateStore
from docforge_core.workflow.e2e_sample_runner import (
    SAMPLE_SOURCE_FILE_NAMES,
    default_e2e_sample_dir,
    load_e2e_sample_project,
)


def test_e2e_sample_fixture_exists() -> None:
    fixture_dir = default_e2e_sample_dir()

    assert fixture_dir.is_dir()
    assert (fixture_dir / "README.md").is_file()
    for relative_path in SAMPLE_SOURCE_FILE_NAMES:
        assert (fixture_dir / relative_path).is_file()


def test_e2e_sample_fixture_has_distinct_corpus_types(tmp_path: Path) -> None:
    store = StateStore(data_dir=tmp_path)
    state = store.create_initial_state()

    result = load_e2e_sample_project(store, state.run_id)

    assert result.imported_count == 6
    reloaded = store.load_state(state.run_id)
    by_name = {item.metadata["fixture_path"]: item for item in reloaded.source_registry}

    assert by_name["reference_soft_copyright.md"].corpus_type == CorpusType.REFERENCE_STYLE
    assert by_name["product_prd.md"].corpus_type == CorpusType.PRODUCT_EVIDENCE
    assert by_name["product_hld.md"].corpus_type == CorpusType.PRODUCT_EVIDENCE
    assert by_name["product_intro.md"].corpus_type == CorpusType.PRODUCT_EVIDENCE
    assert by_name["screenshots/login_page.png"].source_type == SourceType.SCREENSHOT
    assert by_name["screenshots/dashboard_page.png"].source_type == SourceType.SCREENSHOT
    assert all(
        item.metadata.get("sample_fixture") == "e2e_sample"
        for item in reloaded.source_registry
    )


def test_e2e_sample_loader_is_idempotent(tmp_path: Path) -> None:
    store = StateStore(data_dir=tmp_path)
    state = store.create_initial_state()

    first = load_e2e_sample_project(store, state.run_id)
    second = load_e2e_sample_project(store, state.run_id)

    reloaded = store.load_state(state.run_id)
    assert first.imported_count == 6
    assert second.imported_count == 0
    assert second.skipped_existing is True
    assert len(reloaded.source_registry) == 6
    assert reloaded.target_product_name == "墨衡演示数据管理平台"
    assert reloaded.output_requirements["version"] == "V1.0"


def _manual_sample_source(
    fixture_path,
    *,
    source_id: str = "manual_source",
    file_name: str = "saved_name.md",
) -> SourceItem:
    metadata = {"sample_fixture": "e2e_sample"}
    if fixture_path is not None:
        metadata["fixture_path"] = fixture_path
    return SourceItem(
        source_id=source_id,
        source_type=SourceType.PRD,
        file_type=FileType.MD,
        corpus_type=CorpusType.PRODUCT_EVIDENCE,
        allowed_usage=AllowedUsage.FACTUAL_EVIDENCE,
        file_name=file_name,
        file_path=f"/tmp/{file_name}",
        is_reference_source=False,
        is_product_source=True,
        parse_status=ParseStatus.PENDING,
        metadata=metadata,
    )


def test_e2e_sample_loader_rejects_partial_existing_import(tmp_path: Path) -> None:
    store = StateStore(data_dir=tmp_path)
    state = store.create_initial_state()
    store.add_source_item(
        state.run_id,
        _manual_sample_source("reference_soft_copyright.md"),
    )
    before_count = len(store.load_state(state.run_id).source_registry)

    with pytest.raises(ValueError, match="部分导入状态|不完整或异常导入状态"):
        load_e2e_sample_project(store, state.run_id)

    assert len(store.load_state(state.run_id).source_registry) == before_count


def test_e2e_sample_loader_rejects_unknown_existing_fixture_path(
    tmp_path: Path,
) -> None:
    store = StateStore(data_dir=tmp_path)
    state = store.create_initial_state()
    store.add_source_item(state.run_id, _manual_sample_source("unknown.md"))

    with pytest.raises(ValueError, match="不完整或异常导入状态"):
        load_e2e_sample_project(store, state.run_id)


def test_e2e_sample_loader_skips_only_when_all_expected_sources_exist(
    tmp_path: Path,
) -> None:
    store = StateStore(data_dir=tmp_path)
    state = store.create_initial_state()

    first = load_e2e_sample_project(store, state.run_id)
    second = load_e2e_sample_project(store, state.run_id)

    reloaded = store.load_state(state.run_id)
    assert first.imported_count == 6
    assert second.skipped_existing is True
    assert second.imported_count == 0
    assert len(reloaded.source_registry) == 6


def test_e2e_sample_loader_rejects_existing_sample_source_missing_fixture_path(
    tmp_path: Path,
) -> None:
    store = StateStore(data_dir=tmp_path)
    state = store.create_initial_state()
    store.add_source_item(state.run_id, _manual_sample_source(None))

    with pytest.raises(ValueError, match="不完整或异常导入状态"):
        load_e2e_sample_project(store, state.run_id)


def test_e2e_sample_loader_rejects_existing_sample_source_empty_fixture_path(
    tmp_path: Path,
) -> None:
    store = StateStore(data_dir=tmp_path)
    state = store.create_initial_state()
    store.add_source_item(state.run_id, _manual_sample_source(""))

    with pytest.raises(ValueError, match="不完整或异常导入状态"):
        load_e2e_sample_project(store, state.run_id)


def test_e2e_sample_loader_rejects_existing_sample_source_non_string_fixture_path(
    tmp_path: Path,
) -> None:
    store = StateStore(data_dir=tmp_path)
    state = store.create_initial_state()
    store.add_source_item(
        state.run_id,
        _manual_sample_source(["reference_soft_copyright.md"]),
    )

    with pytest.raises(ValueError, match="不完整或异常导入状态"):
        load_e2e_sample_project(store, state.run_id)


def test_e2e_sample_loader_rejects_duplicate_existing_fixture_path(
    tmp_path: Path,
) -> None:
    store = StateStore(data_dir=tmp_path)
    state = store.create_initial_state()
    for index, fixture_path in enumerate(SAMPLE_SOURCE_FILE_NAMES):
        store.add_source_item(
            state.run_id,
            _manual_sample_source(
                fixture_path,
                source_id=f"manual_source_{index}",
                file_name=f"saved_name_{index}.md",
            ),
        )
    store.add_source_item(
        state.run_id,
        _manual_sample_source(
            "product_prd.md",
            source_id="manual_source_duplicate",
            file_name="saved_name_duplicate.md",
        ),
    )

    with pytest.raises(ValueError, match="不完整或异常导入状态|重复 fixture_path"):
        load_e2e_sample_project(store, state.run_id)


def test_e2e_sample_loader_uses_fixture_path_not_saved_filename_for_idempotency(
    tmp_path: Path,
) -> None:
    store = StateStore(data_dir=tmp_path)
    state = store.create_initial_state()
    load_e2e_sample_project(store, state.run_id)
    reloaded = store.load_state(state.run_id)
    for index, source_item in enumerate(reloaded.source_registry):
        source_item.file_name = f"generated_unique_name_{index}.bin"
        source_item.file_path = f"/tmp/generated_unique_name_{index}.bin"
    store.save_state(reloaded)

    second = load_e2e_sample_project(store, state.run_id)

    assert second.skipped_existing is True
    assert second.imported_count == 0
    assert len(store.load_state(state.run_id).source_registry) == 6
