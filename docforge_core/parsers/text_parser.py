"""Plain text parser."""

import re
from pathlib import Path

from .base import BaseParser, ParsedChunk


class TextParser(BaseParser):
    """Parse UTF-8 text into blank-line separated chunks."""

    @property
    def supported_suffixes(self) -> frozenset[str]:
        return frozenset({".txt"})

    def parse(self, path: Path) -> list[ParsedChunk]:
        self.validate_path(path)
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            text = path.read_text(encoding="utf-8-sig")

        parts = [part.strip() for part in re.split(r"\n\s*\n", text)]
        return [
            ParsedChunk(
                text=part,
                source=str(path),
                metadata={"parser": "text", "index": index},
            )
            for index, part in enumerate(parts)
            if part
        ]
