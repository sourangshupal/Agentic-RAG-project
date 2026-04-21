from typing import Dict, List

from pydantic import BaseModel


class JinaEmbeddingRequest(BaseModel):
    """Request model for Jina embeddings API."""

    model: str = "jina-embeddings-v3"
    task: str = "retrieval.passage"  # or "retrieval.query" for queries
    dimensions: int = 1024
    late_chunking: bool = False
    embedding_type: str = "float"
    input: List[str]


class JinaEmbeddingResponse(BaseModel):
    """Response model from Jina embeddings API."""

    model: str
    object: str = "list"
    usage: Dict[str, int]
    data: List[Dict]
