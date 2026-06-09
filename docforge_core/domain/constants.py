"""全局默认常量。运行时值由 Settings 覆盖，此处仅作静态默认。"""

DEFAULT_TOP_K: int = 8
MAX_REVISION_ROUND: int = 3

# 支持的文件扩展名
SUPPORTED_EXTENSIONS: frozenset[str] = frozenset(
    {".docx", ".pdf", ".md", ".txt", ".png", ".jpg", ".jpeg", ".webp"}
)

# Qdrant collection 前缀。实际 collection 名必须是 docforge_{run_id}。
QDRANT_COLLECTION_PREFIX: str = "docforge"

# 向量维度（jina-embeddings-v3 默认）
EMBEDDING_DIM: int = 1024
