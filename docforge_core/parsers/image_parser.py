"""Image parser."""

from pathlib import Path

from .base import BaseParser, ParsedChunk


class ImageParser(BaseParser):
    """Register image files without OCR or visual model parsing."""

    @property
    def supported_suffixes(self) -> frozenset[str]:
        return frozenset({".png", ".jpg", ".jpeg", ".webp"})

    def parse(self, path: Path) -> list[ParsedChunk]:
        self.validate_path(path)
        return [
            ParsedChunk(
                text="图片文件已登记，视觉解析将在后续 Sprint 实现。",
                source=str(path),
                metadata={
                    "parser": "image",
                    "image_path": str(path),
                    "image_suffix": path.suffix.lower(),
                    "visual_parse_status": "pending",
                },
            )
        ]
