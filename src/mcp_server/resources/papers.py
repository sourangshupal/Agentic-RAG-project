import logging
from typing import Any, Dict

from src.mcp_server.server import get_mcp_context, mcp
from src.repositories.paper import PaperRepository

logger = logging.getLogger(__name__)


@mcp.resource("papers://{arxiv_id}")
async def get_paper_resource(arxiv_id: str) -> Dict[str, Any]:
    """Read full metadata and abstract for an arXiv paper.

    URI pattern: papers://{arxiv_id}
    Example:     papers://2310.12402
    """
    ctx = get_mcp_context()

    with ctx.database.get_session() as session:
        repo = PaperRepository(session)
        paper = repo.get_by_arxiv_id(arxiv_id)
        if paper is None and "v" in arxiv_id:
            paper = repo.get_by_arxiv_id(arxiv_id.split("v")[0])
        if paper is None and "v" not in arxiv_id:
            paper = repo.get_by_arxiv_id(f"{arxiv_id}v1")

    if paper is None:
        return {"error": f"Paper {arxiv_id} not found in database"}

    return {
        "arxiv_id": paper.arxiv_id,
        "title": paper.title,
        "authors": paper.authors,
        "abstract": paper.abstract,
        "categories": paper.categories,
        "published_date": paper.published_date.isoformat() if paper.published_date else None,
        "pdf_url": paper.pdf_url,
        "pdf_processed": paper.pdf_processed,
    }


@mcp.resource("index://stats")
async def get_index_stats_resource() -> Dict[str, Any]:
    """Read current OpenSearch index statistics.

    URI: index://stats
    """
    ctx = get_mcp_context()
    return ctx.opensearch_client.get_index_stats()
