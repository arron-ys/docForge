"""
test_state_store.py — StateStore 单元测试

覆盖场景（10 条）：
 1. 可以创建初始 state
 2. 创建 state 时会生成 run 目录
 3. state.json 可以保存
 4. state.json 可以读取，且数据一致
 5. qdrant_collection = docforge_{run_id}
 6. SourceItem 中 source_type = "docx" 应该校验失败
 7. SourceItem 中 file_type = FileType.DOCX 应该校验通过
 8. corpus_type=reference_style 必须对应 allowed_usage=style_only
 9. corpus_type=product_evidence 必须对应 allowed_usage=factual_evidence
10. URL 相关字段默认为空，不参与 MVP 流程
"""

from pathlib import Path

import pytest
from pydantic import ValidationError

from docforge_core.domain.enums import (
    AllowedUsage,
    CorpusType,
    FileType,
    NextAction,
    SourceType,
    WorkflowStatus,
)
from docforge_core.domain.schemas import DocForgeState, SourceItem
from docforge_core.io.state_store import StateStore

# ─── fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture()
def store(tmp_path: Path) -> StateStore:
    """使用 pytest tmp_path 隔离每次测试的文件系统。"""
    return StateStore(data_dir=tmp_path)


@pytest.fixture()
def initial_state(store: StateStore) -> DocForgeState:
    return store.create_initial_state(project_name="测试项目")


# ─── 测试 1：可以创建初始 state ───────────────────────────────────────────────


def test_create_initial_state_returns_docforge_state(store: StateStore) -> None:
    state = store.create_initial_state(project_name="测试项目")

    assert isinstance(state, DocForgeState)
    assert state.project_name == "测试项目"
    assert state.workflow_status == WorkflowStatus.CREATED
    assert state.next_action == NextAction.INGEST_MATERIALS
    assert state.revision_round == 0
    assert state.max_revision_round == 3
    assert state.plan_quality_gate_passed is False
    assert state.source_registry == []
    assert state.parsed_assets == []
    assert state.evidence_map == []
    assert state.draft_versions == []
    assert state.audit_reports == []
    assert state.errors == []
    assert state.warnings == []


# ─── 测试 2：创建 state 时会生成 run 目录 ────────────────────────────────────


def test_create_initial_state_creates_run_directories(
    store: StateStore, tmp_path: Path
) -> None:
    state = store.create_initial_state()

    run_dir = tmp_path / "runs" / state.run_id
    assert run_dir.is_dir(), f"run 目录未创建: {run_dir}"

    expected_subdirs = [
        run_dir / "sources" / "reference",
        run_dir / "sources" / "product",
        run_dir / "sources" / "screenshots",
        run_dir / "parsed",
        run_dir / "evidence",
        run_dir / "drafts",
        run_dir / "audits",
        run_dir / "exports",
    ]
    for sub in expected_subdirs:
        assert sub.is_dir(), f"子目录未创建: {sub}"


# ─── 测试 3：state.json 可以保存 ─────────────────────────────────────────────


def test_save_state_creates_state_json(
    store: StateStore, initial_state: DocForgeState, tmp_path: Path
) -> None:
    state_file = tmp_path / "runs" / initial_state.run_id / "state.json"

    assert state_file.exists(), "state.json 未生成"
    raw = state_file.read_text(encoding="utf-8")
    assert initial_state.run_id in raw, "run_id 未写入 state.json"
    assert "测试项目" in raw, "中文 project_name 未正确写入（可能被转义）"


# ─── 测试 4：state.json 可以读取，且数据一致 ──────────────────────────────────


def test_load_state_returns_same_data(
    store: StateStore, initial_state: DocForgeState
) -> None:
    loaded = store.load_state(initial_state.run_id)

    assert isinstance(loaded, DocForgeState)
    assert loaded.run_id == initial_state.run_id
    assert loaded.project_name == initial_state.project_name
    assert loaded.workflow_status == initial_state.workflow_status
    assert loaded.qdrant_collection == initial_state.qdrant_collection


def test_update_state_saves_validated_updates(
    store: StateStore, initial_state: DocForgeState
) -> None:
    updated = store.update_state(
        initial_state.run_id,
        project_name="更新后的项目",
        workflow_status=WorkflowStatus.MATERIAL_UPLOADED,
    )

    assert updated.project_name == "更新后的项目"
    assert updated.workflow_status == WorkflowStatus.MATERIAL_UPLOADED

    loaded = store.load_state(initial_state.run_id)
    assert loaded.project_name == "更新后的项目"
    assert loaded.workflow_status == WorkflowStatus.MATERIAL_UPLOADED


# ─── 测试 5：qdrant_collection = docforge_{run_id} ──────────────────────────


def test_qdrant_collection_naming(store: StateStore) -> None:
    state = store.create_initial_state()

    assert state.qdrant_collection == f"docforge_{state.run_id}"

    # 加载后命名规则仍然保持
    loaded = store.load_state(state.run_id)
    assert loaded.qdrant_collection == f"docforge_{state.run_id}"


def test_qdrant_collection_must_match_run_id() -> None:
    with pytest.raises(ValidationError, match="qdrant_collection"):
        DocForgeState(run_id="20260605_010203_abcd", qdrant_collection="wrong_collection")


# ─── 测试 6：SourceItem source_type = "docx" 应该校验失败 ────────────────────


def test_source_item_source_type_docx_fails_validation() -> None:
    """
    "docx" 是 FileType 的值，不是 SourceType 的合法值。
    source_type 只能填业务来源类型（如 hld / prd / screenshot），
    不能填文件格式（docx / pdf / png / jpg）。
    """
    with pytest.raises(ValidationError):
        SourceItem(
            source_type="docx",  # type: ignore[arg-type]  # 故意传非法值
            file_type=FileType.DOCX,
            corpus_type=CorpusType.PRODUCT_EVIDENCE,
            allowed_usage=AllowedUsage.FACTUAL_EVIDENCE,
        )


# ─── 测试 7：SourceItem file_type = FileType.DOCX 应该校验通过 ───────────────


def test_source_item_file_type_docx_passes_validation() -> None:
    """
    "docx" 只能填在 file_type 字段，是合法的文件格式类型。
    """
    item = SourceItem(
        source_type=SourceType.HLD,
        file_type=FileType.DOCX,
        corpus_type=CorpusType.PRODUCT_EVIDENCE,
        allowed_usage=AllowedUsage.FACTUAL_EVIDENCE,
        is_product_source=True,
    )
    assert item.file_type == FileType.DOCX
    assert item.source_type == SourceType.HLD


def test_reference_soft_copyright_doc_must_be_reference_source() -> None:
    with pytest.raises(ValidationError, match="is_reference_source"):
        SourceItem(
            source_type=SourceType.REFERENCE_SOFT_COPYRIGHT_DOC,
            file_type=FileType.DOCX,
            corpus_type=CorpusType.REFERENCE_STYLE,
            allowed_usage=AllowedUsage.STYLE_ONLY,
        )


# ─── 测试 8：reference_style 必须对应 style_only ─────────────────────────────


def test_source_item_reference_style_must_use_style_only() -> None:
    """corpus_type=reference_style 时，allowed_usage 必须是 style_only。"""
    # 正确配对 → 应该通过
    item = SourceItem(
        source_type=SourceType.REFERENCE_SOFT_COPYRIGHT_DOC,
        file_type=FileType.DOCX,
        corpus_type=CorpusType.REFERENCE_STYLE,
        allowed_usage=AllowedUsage.STYLE_ONLY,
        is_reference_source=True,
    )
    assert item.corpus_type == CorpusType.REFERENCE_STYLE
    assert item.allowed_usage == AllowedUsage.STYLE_ONLY

    # 错误配对 → 应该校验失败
    with pytest.raises(ValidationError, match="style_only"):
        SourceItem(
            source_type=SourceType.REFERENCE_SOFT_COPYRIGHT_DOC,
            file_type=FileType.DOCX,
            corpus_type=CorpusType.REFERENCE_STYLE,
            allowed_usage=AllowedUsage.FACTUAL_EVIDENCE,  # 错误！
            is_reference_source=True,
        )


# ─── 测试 9：product_evidence 必须对应 factual_evidence ─────────────────────


def test_source_item_product_evidence_must_use_factual_evidence() -> None:
    """corpus_type=product_evidence 时，allowed_usage 必须是 factual_evidence。"""
    # 正确配对 → 应该通过
    item = SourceItem(
        source_type=SourceType.PRD,
        file_type=FileType.PDF,
        corpus_type=CorpusType.PRODUCT_EVIDENCE,
        allowed_usage=AllowedUsage.FACTUAL_EVIDENCE,
        is_product_source=True,
    )
    assert item.corpus_type == CorpusType.PRODUCT_EVIDENCE
    assert item.allowed_usage == AllowedUsage.FACTUAL_EVIDENCE

    # 错误配对 → 应该校验失败
    with pytest.raises(ValidationError, match="factual_evidence"):
        SourceItem(
            source_type=SourceType.PRD,
            file_type=FileType.PDF,
            corpus_type=CorpusType.PRODUCT_EVIDENCE,
            allowed_usage=AllowedUsage.STYLE_ONLY,  # 错误！
            is_product_source=True,
        )


# ─── 测试 10：URL 相关字段默认为空，不参与 MVP 流程 ──────────────────────────


def test_url_fields_default_empty_and_not_in_workflow(store: StateStore) -> None:
    """
    Phase 2 预留字段默认为空：
    - SourceItem.url 默认 None
    - DocForgeState.product_url_source_ids 默认 []
    """
    # SourceItem 的 url 字段默认为 None
    item = SourceItem(
        source_type=SourceType.HLD,
        file_type=FileType.DOCX,
        corpus_type=CorpusType.PRODUCT_EVIDENCE,
        allowed_usage=AllowedUsage.FACTUAL_EVIDENCE,
        is_product_source=True,
    )
    assert item.url is None, "MVP 阶段 url 字段应默认为 None"

    # DocForgeState 的 URL 相关列表默认为空
    state = store.create_initial_state()
    assert state.product_url_source_ids == [], "MVP 阶段不应有 product_url_source_ids"
    assert state.product_source_profile.product_url_ids == []
    assert state.product_source_profile.crawled_pages == []
    assert state.product_source_profile.captured_screenshot_ids == []
    assert state.product_source_profile.failed_urls == []


def _source_item(
    source_id: str,
    source_type: SourceType,
    file_type: FileType,
    is_reference_source: bool,
    is_product_source: bool,
) -> SourceItem:
    corpus_type = (
        CorpusType.REFERENCE_STYLE if is_reference_source else CorpusType.PRODUCT_EVIDENCE
    )
    allowed_usage = (
        AllowedUsage.STYLE_ONLY
        if is_reference_source
        else (
            AllowedUsage.DISPLAY_MATERIAL_ONLY
            if source_type == SourceType.SCREENSHOT
            else AllowedUsage.FACTUAL_EVIDENCE
        )
    )
    return SourceItem(
        source_id=source_id,
        source_type=source_type,
        file_type=file_type,
        corpus_type=corpus_type,
        allowed_usage=allowed_usage,
        file_name=f"{source_id}.{file_type.value}",
        file_path=f"/tmp/{source_id}.{file_type.value}",
        is_reference_source=is_reference_source,
        is_product_source=is_product_source,
    )


def test_add_source_item_appends_reference_source(
    store: StateStore, initial_state: DocForgeState
) -> None:
    source_item = _source_item(
        "src_ref",
        SourceType.REFERENCE_SOFT_COPYRIGHT_DOC,
        FileType.DOCX,
        is_reference_source=True,
        is_product_source=False,
    )

    state = store.add_source_item(initial_state.run_id, source_item)

    assert state.source_registry == [source_item]
    assert state.reference_source_ids == ["src_ref"]


def test_add_source_item_appends_product_source(
    store: StateStore, initial_state: DocForgeState
) -> None:
    source_item = _source_item(
        "src_product",
        SourceType.PRD,
        FileType.PDF,
        is_reference_source=False,
        is_product_source=True,
    )

    state = store.add_source_item(initial_state.run_id, source_item)

    assert state.source_registry == [source_item]
    assert state.product_source_ids == ["src_product"]


def test_add_source_item_appends_screenshot_source(
    store: StateStore, initial_state: DocForgeState
) -> None:
    source_item = _source_item(
        "src_screen",
        SourceType.SCREENSHOT,
        FileType.PNG,
        is_reference_source=False,
        is_product_source=True,
    )

    state = store.add_source_item(initial_state.run_id, source_item)

    assert state.source_registry == [source_item]
    assert state.screenshot_source_ids == ["src_screen"]


def test_add_source_item_updates_reference_source_ids(
    store: StateStore, initial_state: DocForgeState
) -> None:
    source_item = _source_item(
        "src_ref",
        SourceType.REFERENCE_SOFT_COPYRIGHT_DOC,
        FileType.DOCX,
        is_reference_source=True,
        is_product_source=False,
    )

    state = store.add_source_item(initial_state.run_id, source_item)

    assert state.reference_source_ids == [source_item.source_id]


def test_add_source_item_updates_product_source_ids(
    store: StateStore, initial_state: DocForgeState
) -> None:
    source_item = _source_item(
        "src_product",
        SourceType.HLD,
        FileType.DOCX,
        is_reference_source=False,
        is_product_source=True,
    )

    state = store.add_source_item(initial_state.run_id, source_item)

    assert state.product_source_ids == [source_item.source_id]


def test_add_source_item_updates_screenshot_source_ids(
    store: StateStore, initial_state: DocForgeState
) -> None:
    source_item = _source_item(
        "src_screen",
        SourceType.SCREENSHOT,
        FileType.JPG,
        is_reference_source=False,
        is_product_source=True,
    )

    state = store.add_source_item(initial_state.run_id, source_item)

    assert state.screenshot_source_ids == [source_item.source_id]


def test_add_source_item_does_not_update_product_url_source_ids(
    store: StateStore, initial_state: DocForgeState
) -> None:
    source_item = _source_item(
        "src_product",
        SourceType.PRD,
        FileType.PDF,
        is_reference_source=False,
        is_product_source=True,
    )

    state = store.add_source_item(initial_state.run_id, source_item)

    assert state.product_url_source_ids == []


def test_add_source_item_rejects_duplicate_source_id(
    store: StateStore, initial_state: DocForgeState
) -> None:
    source_item = _source_item(
        "src_product",
        SourceType.PRD,
        FileType.PDF,
        is_reference_source=False,
        is_product_source=True,
    )
    store.add_source_item(initial_state.run_id, source_item)

    with pytest.raises(ValueError, match="source_id"):
        store.add_source_item(initial_state.run_id, source_item)


def test_add_source_item_transitions_created_to_material_uploaded(
    store: StateStore, initial_state: DocForgeState
) -> None:
    source_item = _source_item(
        "src_product",
        SourceType.PRD,
        FileType.PDF,
        is_reference_source=False,
        is_product_source=True,
    )

    state = store.add_source_item(initial_state.run_id, source_item)

    assert state.workflow_status == WorkflowStatus.MATERIAL_UPLOADED


def test_add_source_item_sets_next_action_to_parse_sources(
    store: StateStore, initial_state: DocForgeState
) -> None:
    source_item = _source_item(
        "src_product",
        SourceType.PRD,
        FileType.PDF,
        is_reference_source=False,
        is_product_source=True,
    )

    state = store.add_source_item(initial_state.run_id, source_item)

    assert state.next_action == NextAction.PARSE_SOURCES


def test_add_source_item_appends_status_transition_log(
    store: StateStore, initial_state: DocForgeState
) -> None:
    source_item = _source_item(
        "src_product",
        SourceType.PRD,
        FileType.PDF,
        is_reference_source=False,
        is_product_source=True,
    )

    state = store.add_source_item(initial_state.run_id, source_item)

    assert len(state.status_history) == 1
    transition = state.status_history[0]
    assert transition.from_status == WorkflowStatus.CREATED
    assert transition.to_status == WorkflowStatus.MATERIAL_UPLOADED
    assert transition.node_name == "StateStore.add_source_item"
    assert transition.reason == "source material uploaded"


def test_add_source_item_does_not_duplicate_material_uploaded_transition(
    store: StateStore, initial_state: DocForgeState
) -> None:
    first = _source_item(
        "src_product_1",
        SourceType.PRD,
        FileType.PDF,
        is_reference_source=False,
        is_product_source=True,
    )
    second = _source_item(
        "src_product_2",
        SourceType.HLD,
        FileType.DOCX,
        is_reference_source=False,
        is_product_source=True,
    )

    first_state = store.add_source_item(initial_state.run_id, first)
    second_state = store.add_source_item(initial_state.run_id, second)

    assert first_state.workflow_status == WorkflowStatus.MATERIAL_UPLOADED
    assert second_state.workflow_status == WorkflowStatus.MATERIAL_UPLOADED
    assert len(second_state.status_history) == 1
