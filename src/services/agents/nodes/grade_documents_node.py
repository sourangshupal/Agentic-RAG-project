import logging
import time
from typing import Dict

from langgraph.runtime import Runtime

from ..context import Context
from ..models import GradingResult
from ..prompts import GRADE_DOCUMENTS_PROMPT
from ..state import AgentState
from .utils import extract_sources_from_tool_messages, get_latest_context, get_latest_query

logger = logging.getLogger(__name__)


async def ainvoke_grade_documents_step(
    state: AgentState,
    runtime: Runtime[Context],
) -> Dict[str, str | list]:
    """Grade retrieved documents for relevance using LLM.

    This function uses an LLM to evaluate whether the retrieved documents
    are relevant to the user's query and decides whether to generate an
    answer or rewrite the query for better results.

    :param state: Current agent state
    :param runtime: Runtime context
    :returns: Dictionary with routing_decision and grading_results
    """
    logger.info("NODE: grade_documents")
    start_time = time.time()

    # Get query and context
    question = get_latest_query(state["messages"])
    context = get_latest_context(state["messages"])

    # Extract document chunks from context for logging
    chunks_preview = []
    if context:
        # Context is a string containing all documents concatenated
        # Let's show a preview of what was retrieved
        context_preview = context[:500] + "..." if len(context) > 500 else context
        chunks_preview = [{"text_preview": context_preview, "length": len(context)}]

    # Create span for document grading
    span = None
    if runtime.context.langfuse_enabled and runtime.context.trace:
        try:
            span = runtime.context.langfuse_tracer.create_span(
                trace=runtime.context.trace,
                name="document_grading",
                input_data={
                    "query": question,
                    "context_length": len(context) if context else 0,
                    "has_context": context is not None,
                    "chunks_received": chunks_preview,
                },
                metadata={
                    "node": "grade_documents",
                    "model": runtime.context.model_name,
                },
            )
            logger.debug("Created Langfuse span for document grading")
        except Exception as e:
            logger.warning(f"Failed to create span for grade_documents node: {e}")

    if not context:
        logger.warning("No context found, routing to rewrite_query")

        # Update span with no context result
        if span:
            execution_time = (time.time() - start_time) * 1000
            runtime.context.langfuse_tracer.end_span(
                span,
                output={"routing_decision": "rewrite_query", "reason": "no_context"},
                metadata={"execution_time_ms": execution_time},
            )

        return {"routing_decision": "rewrite_query", "grading_results": []}

    logger.debug(f"Grading context of length {len(context)} characters")

    # Use LLM to grade document relevance (plain text — avoids structured output failures on small models)
    try:
        grading_prompt = GRADE_DOCUMENTS_PROMPT.format(
            context=context,
            question=question,
        )

        llm = runtime.context.ollama_client.get_langchain_model(
            model=runtime.context.model_name,
            temperature=0.0,
        )

        logger.info("Invoking LLM for document grading (plain text)")
        grading_response = await llm.ainvoke(grading_prompt)
        response_text = grading_response.content if hasattr(grading_response, "content") else str(grading_response)

        # Look for yes/no in first 300 chars; treat ambiguous output as relevant (fail open)
        snippet = response_text.lower()[:300]
        if '"binary_score": "no"' in snippet or "'binary_score': 'no'" in snippet:
            is_relevant = False
        elif "binary_score" in snippet and "no" in snippet and "yes" not in snippet:
            is_relevant = False
        else:
            is_relevant = True

        score = 1.0 if is_relevant else 0.0
        logger.info(f"LLM grading result: is_relevant={is_relevant}, response_snippet={snippet[:100]}")

        grading_result = GradingResult(
            document_id="retrieved_docs",
            is_relevant=is_relevant,
            score=score,
            reasoning=response_text[:500],
        )

    except Exception as e:
        logger.error(f"LLM grading failed: {e}, failing open")
        # Fail open: if we retrieved any context, attempt to generate an answer
        is_relevant = bool(context.strip())
        grading_result = GradingResult(
            document_id="retrieved_docs",
            is_relevant=is_relevant,
            score=1.0 if is_relevant else 0.0,
            reasoning=f"Fallback (LLM error): {'proceeding with context' if is_relevant else 'no context available'}",
        )

    # Determine routing
    route = "generate_answer" if is_relevant else "rewrite_query"

    logger.info(f"Grading result: {'relevant' if is_relevant else 'not relevant'}, routing to: {route}")

    # Update span with grading result
    if span:
        execution_time = (time.time() - start_time) * 1000
        runtime.context.langfuse_tracer.end_span(
            span,
            output={
                "routing_decision": route,
                "is_relevant": is_relevant,
                "score": score,
                "reasoning": grading_result.reasoning,
            },
            metadata={
                "execution_time_ms": execution_time,
                "context_length": len(context),
            },
        )

    relevant_sources = extract_sources_from_tool_messages(state["messages"]) if is_relevant else []

    return {
        "routing_decision": route,
        "grading_results": [grading_result],
        "relevant_sources": relevant_sources,
    }
