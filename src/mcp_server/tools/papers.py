import logging
from typing import Any, Dict, List, Optional

import logfire
from src.mcp_server.server import get_mcp_context, mcp
from src.models.paper import Paper
from src.repositories.paper import PaperRepository

logger = logging.getLogger(__name__)


def _paper_to_dict(paper: Paper) -> Dict[str, Any]:
    return {
        "id": str(paper.id),
        "arxiv_id": paper.arxiv_id,
        "title": paper.title,
        "authors": paper.authors,
        "abstract": paper.abstract,
        "categories": paper.categories,
        "published_date": paper.published_date.isoformat() if paper.published_date else None,
        "pdf_url": paper.pdf_url,
        "pdf_processed": paper.pdf_processed,
        "created_at": paper.created_at.isoformat() if paper.created_at else None,
    }


@mcp.tool()
async def get_paper_details(arxiv_id: str) -> Optional[Dict[str, Any]]:
    """Fetch full metadata for a specific arXiv paper by its ID.

    Args:
        arxiv_id: arXiv paper ID (e.g. "2310.12402" or "2310.12402v1")

    Returns:
        Paper metadata dict or null if not found in the database
    """
    with logfire.span("mcp:get_paper_details", arxiv_id=arxiv_id):
        ctx = get_mcp_context()

        with ctx.database.get_session() as session:
            repo = PaperRepository(session)
            # Try exact ID first, then without version suffix, then with v1 appended
            paper = repo.get_by_arxiv_id(arxiv_id)
            if paper is None and "v" in arxiv_id:
                paper = repo.get_by_arxiv_id(arxiv_id.split("v")[0])
            if paper is None and "v" not in arxiv_id:
                paper = repo.get_by_arxiv_id(f"{arxiv_id}v1")
            if paper is None:
                return None
            return _paper_to_dict(paper)


@mcp.tool()
async def list_recent_papers(
    limit: int = 10,
    offset: int = 0,
    processed_only: bool = False,
) -> List[Dict[str, Any]]:
    """List recently ingested arXiv papers from the database, ordered by publish date descending.

    Args:
        limit: Number of papers to return (default 10, max 50)
        offset: Pagination offset (default 0)
        processed_only: If True, return only papers with parsed PDF content

    Returns:
        List of paper metadata dicts
    """
    with logfire.span("mcp:list_recent_papers", limit=limit, offset=offset, processed_only=processed_only):
        ctx = get_mcp_context()
        limit = min(limit, 50)

        with ctx.database.get_session() as session:
            repo = PaperRepository(session)
            if processed_only:
                papers = repo.get_processed_papers(limit=limit, offset=offset)
            else:
                papers = repo.get_all(limit=limit, offset=offset)
            return [_paper_to_dict(p) for p in papers]
