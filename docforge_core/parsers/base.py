"""解析器抽象基类。"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class ParsedChunk(BaseModel):
    """单个解析块，携带来源信息。"""

    text: str
    page: int | None = None
    source: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class BaseParser(ABC):
    """所有文件解析器的公共接口。"""

    @abstractmethod
    def parse(self, path: Path) -> list[ParsedChunk]:
        """解析文件并返回文本块列表。"""
        ...

    def supports(self, path: Path) -> bool:
        """子类可重写，默认按 suffix 判断。"""
        return path.suffix.lower() in self.supported_suffixes

    def validate_path(self, path: Path) -> None:
        """Validate existence and suffix before parsing."""
        if not path.exists():
            raise FileNotFoundError(path)
        if not self.supports(path):
            raise ValueError(f"不支持的文件扩展名: {path.suffix}")

    @property
    @abstractmethod
    def supported_suffixes(self) -> frozenset[str]:
        """本解析器支持的文件扩展名集合。"""
        ...
