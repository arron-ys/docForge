"""HTML parser."""

import re
from pathlib import Path

from bs4 import BeautifulSoup

from .base import BaseParser, ParsedChunk


class HtmlParser(BaseParser):
    """Extract visible text from HTML files."""

    @property
    def supported_suffixes(self) -> frozenset[str]:
        return frozenset({".html", ".htm"})

    def parse(self, path: Path) -> list[ParsedChunk]:
        self.validate_path(path)
        html = path.read_text(encoding="utf-8")
        soup = BeautifulSoup(html, "html.parser")
        for element in soup(["script", "style", "noscript"]):
            element.decompose()

        text_parts: list[str] = []
        for tag in soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6", "p", "li"]):
            text = " ".join(tag.get_text(" ", strip=True).split())
            if text:
                text_parts.append(text)

        if not text_parts:
            text = soup.get_text("\n")
            text_parts = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]

        return [
            ParsedChunk(
                text=part,
                source=str(path),
                metadata={"parser": "html", "index": index},
            )
            for index, part in enumerate(text_parts)
        ]
