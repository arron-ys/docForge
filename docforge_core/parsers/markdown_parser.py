"""Markdown parser."""

import re
from pathlib import Path

from .base import BaseParser, ParsedChunk


class MarkdownParser(BaseParser):
    """Parse Markdown text into chunks split by headings or blank lines."""

    @property
    def supported_suffixes(self) -> frozenset[str]:
        return frozenset({".md", ".markdown"})

    def parse(self, path: Path) -> list[ParsedChunk]:
        self.validate_path(path)
        text = path.read_text(encoding="utf-8")
        parts = [part.strip() for part in re.split(r"\n(?=#{1,6}\s)|\n\s*\n", text)]
        return [
            ParsedChunk(
                text=part,
                source=str(path),
                metadata={"parser": "markdown", "index": index},
            )
            for index, part in enumerate(parts)
            if part
        ]
