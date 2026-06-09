"""Run-scoped source file registration for Sprint 2."""

from pathlib import Path

from docforge_core.domain.enums import (
    AllowedUsage,
    CorpusType,
    FileType,
    ParseStatus,
    SourceType,
)
from docforge_core.domain.schemas import SourceItem

from .run_paths import (
    ensure_run_dirs,
    get_product_dir,
    get_reference_dir,
    get_screenshots_dir,
)

REFERENCE_SUFFIXES: frozenset[str] = frozenset({".docx", ".pdf", ".md", ".txt"})
PRODUCT_SUFFIXES: frozenset[str] = frozenset({".docx", ".pdf", ".md", ".txt", ".html"})
SCREENSHOT_SUFFIXES: frozenset[str] = frozenset({".png", ".jpg", ".jpeg", ".webp"})
PRODUCT_SOURCE_TYPES: frozenset[SourceType] = frozenset(
    {
        SourceType.PRODUCT_INTRO_DOC,
        SourceType.PRD,
        SourceType.HLD,
        SourceType.DETAILED_DESIGN_DOC,
        SourceType.OTHER,
    }
)

FILE_TYPE_BY_SUFFIX: dict[str, FileType] = {
    ".docx": FileType.DOCX,
    ".pdf": FileType.PDF,
    ".md": FileType.MD,
    ".txt": FileType.TXT,
    ".html": FileType.HTML,
    ".png": FileType.PNG,
    ".jpg": FileType.JPG,
    ".jpeg": FileType.JPEG,
    ".webp": FileType.WEBP,
}


class SourceFileRegistry:
    """Save uploaded source files under run-scoped source directories."""

    def __init__(self, run_id: str, data_dir: Path | None = None) -> None:
        self.run_id = run_id
        self.data_dir = data_dir
        ensure_run_dirs(run_id, data_dir)

    def register_reference_file(
        self,
        file_name: str,
        content: bytes,
    ) -> SourceItem:
        saved_path = self._save_file(
            directory=get_reference_dir(self.run_id, self.data_dir),
            file_name=file_name,
            content=content,
            allowed_suffixes=REFERENCE_SUFFIXES,
        )
        return SourceItem(
            source_type=SourceType.REFERENCE_SOFT_COPYRIGHT_DOC,
            file_type=self._file_type(saved_path),
            corpus_type=CorpusType.REFERENCE_STYLE,
            allowed_usage=AllowedUsage.STYLE_ONLY,
            file_name=saved_path.name,
            file_path=str(saved_path),
            is_reference_source=True,
            is_product_source=False,
            parse_status=ParseStatus.PENDING,
        )

    def register_product_file(
        self,
        file_name: str,
        content: bytes,
        source_type: SourceType,
    ) -> SourceItem:
        if source_type not in PRODUCT_SOURCE_TYPES:
            raise ValueError(f"不支持的产品资料 source_type: {source_type}")

        saved_path = self._save_file(
            directory=get_product_dir(self.run_id, self.data_dir),
            file_name=file_name,
            content=content,
            allowed_suffixes=PRODUCT_SUFFIXES,
        )
        return SourceItem(
            source_type=source_type,
            file_type=self._file_type(saved_path),
            corpus_type=CorpusType.PRODUCT_EVIDENCE,
            allowed_usage=AllowedUsage.FACTUAL_EVIDENCE,
            file_name=saved_path.name,
            file_path=str(saved_path),
            is_reference_source=False,
            is_product_source=True,
            parse_status=ParseStatus.PENDING,
        )

    def register_screenshot_file(self, file_name: str, content: bytes) -> SourceItem:
        saved_path = self._save_file(
            directory=get_screenshots_dir(self.run_id, self.data_dir),
            file_name=file_name,
            content=content,
            allowed_suffixes=SCREENSHOT_SUFFIXES,
        )
        return SourceItem(
            source_type=SourceType.SCREENSHOT,
            file_type=self._file_type(saved_path),
            corpus_type=CorpusType.PRODUCT_EVIDENCE,
            allowed_usage=AllowedUsage.DISPLAY_MATERIAL_ONLY,
            file_name=saved_path.name,
            file_path=str(saved_path),
            is_reference_source=False,
            is_product_source=True,
            parse_status=ParseStatus.PENDING,
        )

    def _save_file(
        self,
        directory: Path,
        file_name: str,
        content: bytes,
        allowed_suffixes: frozenset[str],
    ) -> Path:
        safe_name = self._safe_file_name(file_name)
        suffix = Path(safe_name).suffix.lower()
        if suffix not in allowed_suffixes:
            allowed = ", ".join(sorted(allowed_suffixes))
            raise ValueError(f"不支持的文件扩展名: {suffix or '<none>'}，允许: {allowed}")

        directory.mkdir(parents=True, exist_ok=True)
        target = self._unique_path(directory / safe_name)
        target.write_bytes(content)
        return target

    @staticmethod
    def _safe_file_name(file_name: str) -> str:
        safe_name = Path(file_name.replace("\\", "/")).name.strip()
        if not safe_name or safe_name in {".", ".."}:
            raise ValueError("文件名不能为空")
        return safe_name

    @staticmethod
    def _unique_path(path: Path) -> Path:
        if not path.exists():
            return path

        stem = path.stem
        suffix = path.suffix
        parent = path.parent
        index = 1
        while True:
            candidate = parent / f"{stem}_{index}{suffix}"
            if not candidate.exists():
                return candidate
            index += 1

    @staticmethod
    def _file_type(path: Path) -> FileType:
        try:
            return FILE_TYPE_BY_SUFFIX[path.suffix.lower()]
        except KeyError as exc:
            raise ValueError(f"不支持的文件扩展名: {path.suffix}") from exc
