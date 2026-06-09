"""PDF parser."""

from pathlib import Path

from pypdf import PdfReader

from .base import BaseParser, ParsedChunk


class PdfParser(BaseParser):
    """Parse PDF text by page using pypdf with PyMuPDF fallback."""

    @property
    def supported_suffixes(self) -> frozenset[str]:
        return frozenset({".pdf"})

    def parse(self, path: Path) -> list[ParsedChunk]:
        self.validate_path(path)
        chunks: list[ParsedChunk] = []
        page_count = 0

        pypdf_open_failed = False
        try:
            reader = PdfReader(str(path))
            page_count = len(reader.pages)
            for index, page in enumerate(reader.pages, start=1):
                text = ""
                try:
                    text = page.extract_text() or ""
                except Exception:
                    text = self._extract_page_with_pymupdf(path, index)
                text = text.strip()
                if text:
                    chunks.append(
                        ParsedChunk(
                            text=text,
                            page=index,
                            source=str(path),
                            metadata={"parser": "pdf", "page": index},
                        )
                    )
        except Exception:
            pypdf_open_failed = True
            chunks = self._parse_with_pymupdf(path)

        if pypdf_open_failed and not chunks:
            raise ValueError(f"PDF 文件无法打开或已损坏: {path}")
        if not chunks and page_count:
            return []
        return chunks

    @staticmethod
    def _extract_page_with_pymupdf(path: Path, page_number: int) -> str:
        try:
            import fitz

            with fitz.open(path) as document:
                page = document.load_page(page_number - 1)
                return page.get_text() or ""
        except Exception:
            return ""

    @staticmethod
    def _parse_with_pymupdf(path: Path) -> list[ParsedChunk]:
        try:
            import fitz

            chunks: list[ParsedChunk] = []
            with fitz.open(path) as document:
                for index, page in enumerate(document, start=1):
                    text = (page.get_text() or "").strip()
                    if text:
                        chunks.append(
                            ParsedChunk(
                                text=text,
                                page=index,
                                source=str(path),
                                metadata={"parser": "pdf", "page": index},
                            )
                        )
            return chunks
        except Exception:
            return []
