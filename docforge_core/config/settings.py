from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # 运行环境
    docforge_env: str = "local"
    docforge_data_dir: Path = Path("data")
    docforge_qdrant_path: Path = Path("data/qdrant")

    # 默认提供商
    default_llm_provider: str = "qwen"
    default_embedding_provider: str = "jina"

    # Qwen
    qwen_api_key: str = ""
    qwen_base_url: str = ""
    qwen_model: str = "qwen-plus"

    # DeepSeek
    deepseek_api_key: str = ""
    deepseek_base_url: str = ""
    deepseek_model: str = "deepseek-chat"

    # Jina Embedding
    jina_api_key: str = ""
    jina_embedding_model: str = "jina-embeddings-v3"
    jina_base_url: str = "https://api.jina.ai/v1"

    # 生成参数
    max_revision_round: int = 3
    default_top_k: int = 8

    @field_validator("docforge_data_dir", "docforge_qdrant_path", mode="before")
    @classmethod
    def _to_path(cls, v: object) -> Path:
        return Path(str(v))


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
