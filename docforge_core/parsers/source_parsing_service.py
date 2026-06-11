"""Source parsing orchestration for Sprint 3."""

from pathlib import Path

from docforge_core.domain.enums import (
    AssetType,
    FileType,
    NextAction,
    ParseStatus,
    SourceType,
    WorkflowStatus,
)
from docforge_core.domain.schemas import DocForgeState, ParsedAsset, SourceItem, StateTransitionLog
from docforge_core.io.run_paths import get_parsed_dir, get_run_dir
from docforge_core.io.state_store import StateStore

from .base import BaseParser, ParsedChunk
from .docx_parser import DocxParser
from .html_parser import HtmlParser
from .image_parser import ImageParser
from .markdown_parser import MarkdownParser
from .pdf_parser import PdfParser
from .text_parser import TextParser


class SourceParsingService:
    """Parse pending SourceItem records into ParsedAsset records."""

    def __init__(self, data_dir: Path | None = None) -> None:
        self.data_dir = data_dir
        self.state_store = StateStore(data_dir=data_dir)
        self.parsers: dict[FileType, BaseParser] = {
            FileType.DOCX: DocxParser(),
            FileType.PDF: PdfParser(),
            FileType.MD: MarkdownParser(),
            FileType.TXT: TextParser(),
            FileType.HTML: HtmlParser(),
            FileType.PNG: ImageParser(),
            FileType.JPG: ImageParser(),
            FileType.JPEG: ImageParser(),
            FileType.WEBP: ImageParser(),
        }

    def parse_run(self, run_id: str) -> DocForgeState:
        state = self.state_store.load_state(run_id)
        run_dir = get_run_dir(run_id, self.data_dir)
        parsed_assets: list[ParsedAsset] = []
        success_count = 0

        for source_item in state.source_registry:
            if source_item.parse_status != ParseStatus.PENDING:
                continue
            try:
                source_assets = self._parse_source(run_dir, run_id, source_item)
            except Exception as exc:
                source_item.parse_status = ParseStatus.FAILED
                source_item.parse_error = str(exc)
                continue

            source_item.parse_status = ParseStatus.PARSED
            source_item.parse_error = None
            parsed_assets.extend(source_assets)
            success_count += 1

        state.parsed_assets.extend(parsed_assets)

        if success_count > 0 and state.workflow_status == WorkflowStatus.MATERIAL_UPLOADED:
            state.status_history.append(
                StateTransitionLog(
                    from_status=WorkflowStatus.MATERIAL_UPLOADED,
                    to_status=WorkflowStatus.SOURCE_PARSED,
                    node_name="SourceParsingService.parse_run",
                    reason="source materials parsed",
                )
            )
            state.workflow_status = WorkflowStatus.SOURCE_PARSED
            state.next_action = NextAction.ANALYZE_REFERENCE_STYLE

        self.state_store.save_state(state)
        return state

    def _parse_source(
        self,
        run_dir: Path,
        run_id: str,
        source_item: SourceItem,
    ) -> list[ParsedAsset]:
        if not source_item.file_path:
            raise ValueError("SourceItem.file_path 不能为空")

        parser = self.parsers.get(source_item.file_type)
        if parser is None:
            raise ValueError(f"不支持的 file_type: {source_item.file_type}")

        source_path = self._resolve_source_path(run_dir, source_item.file_path)
        if not source_path.exists():
            raise FileNotFoundError("找不到已上传文件，请重新上传资料。")
        chunks = parser.parse(source_path)

        if isinstance(parser, ImageParser):
            return [self._image_asset(run_dir, source_item, source_path)]

        return self._text_assets(run_dir, run_id, source_item, chunks)

    @staticmethod
    def _resolve_source_path(run_dir: Path, file_path: str) -> Path:
        raw_path = Path(file_path)
        if raw_path.is_absolute():
            resolved = raw_path.resolve()
        else:
            run_dir_resolved = run_dir.resolve()
            resolved = (run_dir / raw_path).resolve()
            if not resolved.exists():
                legacy_resolved = raw_path.resolve()
                try:
                    legacy_resolved.relative_to(run_dir_resolved)
                except ValueError:
                    pass
                else:
                    resolved = legacy_resolved
        run_dir_resolved = run_dir.resolve()
        try:
            resolved.relative_to(run_dir_resolved)
        except ValueError as exc:
            raise ValueError("已上传文件路径非法，请重新上传资料。") from exc
        return resolved

    def _text_assets(
        self,
        run_dir: Path,
        run_id: str,
        source_item: SourceItem,
        chunks: list[ParsedChunk],
    ) -> list[ParsedAsset]:
        parsed_dir = get_parsed_dir(run_id, self.data_dir) / source_item.source_id
        parsed_dir.mkdir(parents=True, exist_ok=True)

        assets: list[ParsedAsset] = []
        for index, chunk in enumerate(chunks, start=1):
            chunk_path = parsed_dir / f"chunk_{index:03d}.txt"
            chunk_path.write_text(chunk.text, encoding="utf-8")
            ref = chunk_path.relative_to(run_dir)
            summary = " ".join(chunk.text.split())[:120]
            assets.append(
                ParsedAsset(
                    source_id=source_item.source_id,
                    asset_type=AssetType.TEXT,
                    title=source_item.file_name,
                    summary=summary,
                    extracted_text_ref=str(ref),
                    page_number=chunk.page,
                    confidence=1.0,
                )
            )
        return assets

    @staticmethod
    def _image_asset(run_dir: Path, source_item: SourceItem, source_path: Path) -> ParsedAsset:
        asset_type = (
            AssetType.SCREENSHOT
            if source_item.source_type == SourceType.SCREENSHOT
            else AssetType.IMAGE
        )
        return ParsedAsset(
            source_id=source_item.source_id,
            asset_type=asset_type,
            title=source_item.file_name,
            summary="图片文件已登记，视觉解析将在后续 Sprint 实现。",
            extracted_text_ref=None,
            image_ref=str(source_path.relative_to(run_dir)),
            confidence=1.0,
        )
