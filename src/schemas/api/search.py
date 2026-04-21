from typing import List, Optional

from pydantic import BaseModel, Field


class SearchRequest(BaseModel):
    """Search request model."""

    query: str = Field(..., min_length=1, max_length=500, description="Search query across title, abstract, and authors")
    size: int = Field(default=10, ge=1, le=50, description="Number of results to return")
    from_: int = Field(default=0, ge=0, alias="from", description="Offset for pagination")
    categories: Optional[List[str]] = Field(default=None, description="Filter by categories")
    latest_papers: bool = Field(default=False, description="Sort by publication date (newest first) instead of relevance")


class HybridSearchRequest(BaseModel):
    """Request model for hybrid search supporting all search modes."""

    query: str = Field(..., description="Search query text", min_length=1, max_length=500)
    size: int = Field(10, description="Number of results to return", ge=1, le=100)
    from_: int = Field(0, description="Offset for pagination", ge=0, alias="from")
    categories: Optional[List[str]] = Field(None, description="Filter by arXiv categories (e.g., ['cs.AI', 'cs.LG'])")
    latest_papers: bool = Field(False, description="Sort by publication date instead of relevance")
    use_hybrid: bool = Field(True, description="Enable hybrid search (BM25 + vector) with automatic embedding generation")
    min_score: float = Field(0.0, description="Minimum score threshold for results", ge=0.0)

    class Config:
        populate_by_name = True
        json_schema_extra = {
            "example": {
                "query": "machine learning neural networks",
                "size": 10,
                "categories": ["cs.AI", "cs.LG"],
                "latest_papers": False,
                "use_hybrid": True,
            }
        }


class SearchHit(BaseModel):
    """Individual search result."""

    arxiv_id: str
    title: str
    authors: Optional[str]
    abstract: Optional[str]
    published_date: Optional[str]
    pdf_url: Optional[str]
    score: float
    highlights: Optional[dict] = None

    # Chunk-specific fields (for unified search)
    chunk_text: Optional[str] = Field(None, description="Text content of the matching chunk")
    chunk_id: Optional[str] = Field(None, description="Unique identifier of the chunk")
    section_name: Optional[str] = Field(None, description="Section name where the chunk was found")


class SearchResponse(BaseModel):
    """Search response model."""

    query: str
    total: int
    hits: List[SearchHit]
    size: int = Field(description="Number of results requested")
    from_: int = Field(alias="from", description="Offset used for pagination")
    search_mode: Optional[str] = Field(None, description="Search mode used: bm25, vector, or hybrid")
    error: Optional[str] = None

    class Config:
        populate_by_name = True
