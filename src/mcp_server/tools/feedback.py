import logging
from typing import Any, Dict, Optional

import logfire
from src.mcp_server.server import get_mcp_context, mcp

logger = logging.getLogger(__name__)


@mcp.tool()
async def submit_feedback(
    trace_id: str,
    score: float,
    comment: Optional[str] = None,
) -> Dict[str, Any]:
    """Submit quality feedback for a previous ask_question response via Langfuse.

    Args:
        trace_id: Trace ID returned from a previous ask_question call (visible in Langfuse)
        score: Feedback score between -1.0 (bad) and 1.0 (good)
        comment: Optional free-text comment about the response quality

    Returns:
        dict with success bool and message
    """
    with logfire.span("mcp:submit_feedback", trace_id=trace_id, score=score):
        ctx = get_mcp_context()

        if ctx.langfuse_tracer is None:
            return {"success": False, "message": "Langfuse tracing is not configured"}

        if not (-1.0 <= score <= 1.0):
            return {"success": False, "message": "Score must be between -1.0 and 1.0"}

        success = ctx.langfuse_tracer.submit_feedback(
            trace_id=trace_id,
            score=score,
            name="mcp-feedback",
            comment=comment,
        )

        return {
            "success": success,
            "message": "Feedback submitted" if success else "Failed to submit feedback — check Langfuse configuration",
        }


@mcp.tool()
async def get_index_stats() -> Dict[str, Any]:
    """Get statistics about the OpenSearch paper index.

    Returns:
        dict with index_name, exists, document_count, size_in_bytes
    """
    with logfire.span("mcp:get_index_stats"):
        ctx = get_mcp_context()
        return ctx.opensearch_client.get_index_stats()
