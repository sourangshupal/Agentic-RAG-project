import logging
import time
from typing import Dict, List

import logfire
from langchain_core.messages import AIMessage
from langgraph.runtime import Runtime

from ..context import Context
from ..state import AgentState

logger = logging.getLogger(__name__)

GROUNDING_FAIL_MESSAGE = (
    "I'm sorry, but I cannot provide an answer that is sufficiently supported by the "
    "retrieved research papers. The documents retrieved may not contain enough information "
    "to reliably answer your question. Please try rephrasing your query or asking about "
    "a different aspect of the topic."
)


@logfire.instrument("node:output_guardrail", extract_args=False)
async def ainvoke_output_guardrail_step(
    state: AgentState,
    runtime: Runtime[Context],
) -> Dict[str, List[AIMessage]]:
    """Verify the generated answer is grounded in retrieved source documents.

    Uses AWS Bedrock Guardrails OUTPUT check to apply:
    - Content filters on the generated answer
    - Grounding check: score answer against retrieved source texts

    If the answer fails grounding, it is replaced with a safe fallback message.
    When no guardrails service is configured, this node is a transparent pass-through.

    :param state: Current agent state
    :param runtime: Runtime context
    :returns: Empty dict (pass-through) or dict with replacement AIMessage
    """
    logger.info("NODE: output_guardrail")

    if not runtime.context.guardrails_service:
        logger.debug("No guardrails service — output_guardrail is a pass-through")
        return {}

    # Extract the generated answer from the last message
    messages = state.get("messages", [])
    if not messages:
        return {}

    last_msg = messages[-1]
    answer = last_msg.content if hasattr(last_msg, "content") else str(last_msg)

    if not answer or not answer.strip():
        return {}

    # Get the original query for grounding evaluation
    from .utils import get_latest_query
    query = state.get("sanitized_query") or get_latest_query(state.get("messages", []))

    # Collect source document texts for grounding check
    # Use actual retrieved chunk context — titles alone are insufficient for grounding
    source_texts: List[str] = []
    from .utils import get_latest_context
    context = get_latest_context(state.get("messages", []))
    if context:
        # Split context into chunks (tool messages may concatenate multiple docs)
        source_texts = [chunk.strip() for chunk in context.split("\n\n") if chunk.strip()]

    # Fall back to titles if no context available
    if not source_texts:
        for source in state.get("relevant_sources", []):
            title = getattr(source, "title", "")
            abstract = getattr(source, "abstract", "")
            arxiv_id = getattr(source, "arxiv_id", "")
            text = abstract or title
            if text:
                source_texts.append(f"{text} (arXiv:{arxiv_id})")

    # If no source texts available, skip grounding check
    if not source_texts:
        logger.debug("No source texts available — skipping output grounding check")
        return {}

    span = None
    if runtime.context.langfuse_enabled and runtime.context.trace:
        try:
            span = runtime.context.langfuse_tracer.create_span(
                trace=runtime.context.trace,
                name="output_guardrail_check",
                input_data={
                    "query": query,
                    "answer_length": len(answer),
                    "source_count": len(source_texts),
                },
                metadata={"node": "output_guardrail"},
            )
        except Exception as e:
            logger.warning(f"Failed to create Langfuse span for output guardrail: {e}")

    start_time = time.time()
    try:
        result = await runtime.context.guardrails_service.check_output(answer, source_texts, query=query)

        if span:
            execution_time = (time.time() - start_time) * 1000
            runtime.context.langfuse_tracer.end_span(
                span,
                output={
                    "action": result.action,
                    "allowed": result.allowed,
                    "reason": result.reason,
                },
                metadata={"execution_time_ms": execution_time},
            )

        if not result.allowed:
            logger.warning(f"Output guardrail blocked answer: {result.reason}")
            return {
                "messages": [AIMessage(content=GROUNDING_FAIL_MESSAGE)],
                "output_guardrail_filter": result.reason,
            }

        logger.info(f"Output guardrail passed: {result.reason}")
        return {"output_guardrail_filter": result.reason}

    except Exception as e:
        logger.error(f"Output guardrail check failed: {e} — passing answer through")
        if span:
            execution_time = (time.time() - start_time) * 1000
            runtime.context.langfuse_tracer.update_span(
                span,
                output={"error": str(e), "fallback": True},
                metadata={"execution_time_ms": execution_time},
                level="WARNING",
            )
            runtime.context.langfuse_tracer.end_span(span)
        return {}
