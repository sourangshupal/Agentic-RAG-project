from src.schemas.api.health import HealthResponse, ServiceStatus
from src.schemas.api.search import SearchHit, SearchRequest, SearchResponse

# ArXiv schemas
from src.schemas.arxiv.paper import (
    ArxivPaper,
    PaperBase,
    PaperCreate,
    PaperResponse,
    PaperSearchResponse,
)

# Database schemas
from src.schemas.database.config import PostgreSQLSettings

# Embeddings schemas
from src.schemas.embeddings.jina import JinaEmbeddingRequest, JinaEmbeddingResponse

# Indexing schemas (including chunking)
from src.schemas.indexing.models import ChunkMetadata, TextChunk

# PDF Parser schemas
from src.schemas.pdf_parser.models import (
    ArxivMetadata,
    PaperFigure,
    PaperSection,
    PaperTable,
    ParsedPaper,
    ParserType,
    PdfContent,
)

# Search schemas
from src.schemas.search.hybrid import (
    ChunkResult,
    HybridSearchRequest,
    HybridSearchResponse,
)

__all__ = [
    # API
    "HealthResponse",
    "ServiceStatus",
    "SearchRequest",
    "SearchResponse",
    "SearchHit",
    # ArXiv
    "ArxivPaper",
    "PaperBase",
    "PaperCreate",
    "PaperResponse",
    "PaperSearchResponse",
    # Indexing
    "ChunkMetadata",
    "TextChunk",
    # Database
    "PostgreSQLSettings",
    # Embeddings
    "JinaEmbeddingRequest",
    "JinaEmbeddingResponse",
    # PDF Parser
    "ParserType",
    "PaperSection",
    "PaperFigure",
    "PaperTable",
    "PdfContent",
    "ArxivMetadata",
    "ParsedPaper",
    # Search
    "HybridSearchRequest",
    "HybridSearchResponse",
    "ChunkResult",
]
