import logging
from dataclasses import dataclass
from typing import Optional

from fastmcp import FastMCP
from src.db.interfaces.base import BaseDatabase
from src.services.agents.agentic_rag import AgenticRAGService
from src.services.embeddings.jina_client import JinaEmbeddingsClient
from src.services.langfuse.client import LangfuseTracer
from src.services.openai_llm.client import OpenAILLMClient
from src.services.opensearch.client import OpenSearchClient

logger = logging.getLogger(__name__)

mcp = FastMCP(
    name="arxiv-rag",
    instructions=(
        "Search and query arXiv CS/AI/ML papers using a production-grade hybrid RAG system. "
        "Available tools: search_papers (BM25+vector), ask_question (full agentic pipeline), "
        "get_paper_details, list_recent_papers, submit_feedback, get_index_stats."
    ),
)


@dataclass
class MCPContext:
    opensearch_client: OpenSearchClient
    embeddings_client: JinaEmbeddingsClient
    llm_client: OpenAILLMClient
    langfuse_tracer: Optional[LangfuseTracer]
    agentic_rag_service: AgenticRAGService
    database: BaseDatabase


_mcp_context: Optional[MCPContext] = None


def set_mcp_context(ctx: MCPContext) -> None:
    global _mcp_context
    _mcp_context = ctx
    logger.info("MCP context initialized")


def get_mcp_context() -> MCPContext:
    if _mcp_context is None:
        raise RuntimeError("MCP context not initialized — services must be started first")
    return _mcp_context


# Import tool/resource modules to trigger @mcp.tool() / @mcp.resource() registration.
# These imports MUST stay at the bottom — `mcp` must be defined first.
import src.mcp_server.tools.ask  # noqa: E402, F401
import src.mcp_server.tools.feedback  # noqa: E402, F401
import src.mcp_server.tools.papers  # noqa: E402, F401
import src.mcp_server.tools.search  # noqa: E402, F401
import src.mcp_server.resources.papers  # noqa: E402, F401
