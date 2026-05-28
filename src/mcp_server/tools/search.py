import logging
from typing import Any, Dict, List, Optional

import logfire
from pydantic import BaseModel
from src.mcp_server.server import get_mcp_context, mcp

logger = logging.getLogger(__name__)


class ChunkResult(BaseModel):
    chunk_id: str
    arxiv_id: str
    title: str
    authors: List[str]
    abstract: Optional[str]
    chunk_text: str
    section_title: Optional[str]
    score: float


@mcp.tool()
async def search_papers(
    query: str,
    top_k: int = 5,
    use_hybrid: bool = True,
) -> List[Dict[str, Any]]:
    """Search indexed arXiv CS/AI/ML paper chunks using BM25 + semantic vector search (hybrid RRF).

    Args:
        query: Natural language search query
        top_k: Number of chunks to return (default 5, max 20)
        use_hybrid: Use hybrid BM25+vector search; False = BM25 only (default True)

    Returns:
        List of matching chunks with arxiv_id, title, authors, chunk_text, score
    """
    with logfire.span("mcp:search_papers", query=query[:120], top_k=top_k, use_hybrid=use_hybrid):
        ctx = get_mcp_context()
        top_k = min(top_k, 20)

        query_embedding: Optional[List[float]] = None
        if use_hybrid:
            try:
                query_embedding = await ctx.embeddings_client.embed_query(query)
            except Exception as e:
                logger.warning(f"Embedding failed, falling back to BM25: {e}")

        results = ctx.opensearch_client.search_unified(
            query=query,
            query_embedding=query_embedding,
            size=top_k,
            use_hybrid=use_hybrid and query_embedding is not None,
        )

        hits = results.get("hits", [])
        return [
            {
                "chunk_id": hit.get("chunk_id", ""),
                "arxiv_id": hit.get("arxiv_id", ""),
                "title": hit.get("title", ""),
                "authors": hit.get("authors", []),
                "abstract": hit.get("abstract"),
                "chunk_text": hit.get("chunk_text", ""),
                "section_title": hit.get("section_title"),
                "score": round(float(hit.get("score", 0.0)), 4),
            }
            for hit in hits
        ]
