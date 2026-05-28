import logging
from typing import Any, Dict, Optional

import logfire
from src.mcp_server.server import get_mcp_context, mcp

logger = logging.getLogger(__name__)


@mcp.tool()
async def ask_question(
    query: str,
    model: Optional[str] = None,
) -> Dict[str, Any]:
    """Ask a research question about arXiv papers using the full agentic RAG pipeline.

    The pipeline includes:
    - Guardrail check (CS/AI/ML scope validation)
    - Hybrid document retrieval (BM25 + vector)
    - LLM-based relevance grading
    - Query rewriting if documents are not relevant
    - Answer generation with source attribution

    Args:
        query: Research question about CS, AI, or ML papers
        model: Optional OpenAI model override (default: gpt-4o-mini)

    Returns:
        dict with keys: query, answer, sources, reasoning_steps,
        retrieval_attempts, rewritten_query, execution_time, guardrail_score,
        trace_id (pass to submit_feedback to rate this response)
    """
    with logfire.span("mcp:ask_question", query=query[:120], model=model or "gpt-4o-mini"):
        ctx = get_mcp_context()

        result = await ctx.agentic_rag_service.ask(
            query=query,
            user_id="mcp-client",
            model=model,
        )

        return {
            "query": result.get("query", query),
            "answer": result.get("answer", ""),
            "sources": result.get("sources", []),
            "reasoning_steps": result.get("reasoning_steps", []),
            "retrieval_attempts": result.get("retrieval_attempts", 0),
            "rewritten_query": result.get("rewritten_query"),
            "execution_time_seconds": round(result.get("execution_time", 0.0), 2),
            "guardrail_score": result.get("guardrail_score"),
            "trace_id": result.get("trace_id"),
        }
