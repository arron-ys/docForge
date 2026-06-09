from __future__ import annotations

import shutil
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile

from api.errors import state_not_found, upload_file_not_allowed, upload_save_failed
from api.schemas import SourceItemView
from api.state_mapper import to_source_view
from docforge_core.domain.enums import AllowedUsage, CorpusType, FileType, ParseStatus, SourceType
from docforge_core.domain.schemas import SourceItem
from docforge_core.io.run_paths import get_product_dir, get_reference_dir, get_screenshots_dir
from docforge_core.io.state_store import StateStore

ALLOWED_DOCUMENT_TYPES = {FileType.DOCX, FileType.PDF, FileType.MD, FileType.TXT, FileType.HTML}
ALLOWED_IMAGE_TYPES = {FileType.PNG, FileType.JPG, FileType.JPEG, FileType.WEBP}


class SourceUploadService:
    def __init__(self, state_store: StateStore) -> None:
        self.state_store = state_store

    def upload_reference(self, run_id: str, file: UploadFile) -> SourceItemView:
        return self._upload(
            run_id=run_id,
            file=file,
            target_dir=get_reference_dir(run_id, self.state_store.data_dir),
            source_type=SourceType.REFERENCE_SOFT_COPYRIGHT_DOC,
            corpus_type=CorpusType.REFERENCE_STYLE,
            allowed_usage=AllowedUsage.STYLE_ONLY,
            is_reference_source=True,
            is_product_source=False,
            allowed_file_types=ALLOWED_DOCUMENT_TYPES,
            notes="外部参考软著只能用于目录结构、章法、配图方式和语言风格参考，不能作为产品事实来源。",
        )

    def upload_product(self, run_id: str, file: UploadFile) -> SourceItemView:
        return self._upload(
            run_id=run_id,
            file=file,
            target_dir=get_product_dir(run_id, self.state_store.data_dir),
            source_type=SourceType.PRODUCT_INTRO_DOC,
            corpus_type=CorpusType.PRODUCT_EVIDENCE,
            allowed_usage=AllowedUsage.FACTUAL_EVIDENCE,
            is_reference_source=False,
            is_product_source=True,
            allowed_file_types=ALLOWED_DOCUMENT_TYPES,
            notes="自有产品资料可用于产品能力描述和事实归纳。",
        )

    def upload_screenshot(self, run_id: str, file: UploadFile) -> SourceItemView:
        return self._upload(
            run_id=run_id,
            file=file,
            target_dir=get_screenshots_dir(run_id, self.state_store.data_dir),
            source_type=SourceType.SCREENSHOT,
            corpus_type=CorpusType.PRODUCT_EVIDENCE,
            allowed_usage=AllowedUsage.DISPLAY_MATERIAL_ONLY,
            is_reference_source=False,
            is_product_source=True,
            allowed_file_types=ALLOWED_IMAGE_TYPES,
            notes="当前阶段截图仅作为展示素材和配图候选，MVP 不做 OCR，不作为强产品事实证据。",
        )

    def _upload(
        self,
        *,
        run_id: str,
        file: UploadFile,
        target_dir: Path,
        source_type: SourceType,
        corpus_type: CorpusType,
        allowed_usage: AllowedUsage,
        is_reference_source: bool,
        is_product_source: bool,
        allowed_file_types: set[FileType],
        notes: str,
    ) -> SourceItemView:
        try:
            self.state_store.load_state(run_id)
        except FileNotFoundError as exc:
            raise state_not_found(run_id) from exc

        file_type = file_type_from_name(file.filename or "")
        if file_type not in allowed_file_types:
            raise upload_file_not_allowed("上传文件类型不支持或与资料类型不匹配。")

        target_dir.mkdir(parents=True, exist_ok=True)
        safe_name = safe_filename(file.filename or f"upload.{file_type.value}")
        stored_name = f"{uuid4().hex}_{safe_name}"
        target_path = target_dir / stored_name
        try:
            with target_path.open("wb") as output:
                shutil.copyfileobj(file.file, output)
        except Exception as exc:
            raise upload_save_failed() from exc

        relative_path = target_path.relative_to(self.state_store.data_dir / "runs" / run_id)
        source = SourceItem(
            source_type=source_type,
            file_type=file_type,
            corpus_type=corpus_type,
            allowed_usage=allowed_usage,
            file_name=file.filename,
            file_path=str(relative_path),
            is_reference_source=is_reference_source,
            is_product_source=is_product_source,
            parse_status=ParseStatus.PENDING,
            notes=notes,
            metadata={"file_size": target_path.stat().st_size},
        )
        updated = self.state_store.add_source_item(run_id, source)
        return to_source_view(run_id, updated.source_registry[-1])


def file_type_from_name(file_name: str) -> FileType:
    suffix = Path(file_name).suffix.lower().lstrip(".")
    try:
        return FileType(suffix)
    except ValueError:
        return FileType.OTHER


def safe_filename(file_name: str) -> str:
    name = Path(file_name).name.strip() or "upload.bin"
    return "".join(char if char.isalnum() or char in {".", "-", "_"} else "_" for char in name)
