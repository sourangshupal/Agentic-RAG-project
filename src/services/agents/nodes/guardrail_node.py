import logging
import time
from typing import Dict, Literal

import logfire
from langgraph.runtime import Runtime

from ..context import Context
from ..models import GuardrailScoring
from ..state import AgentState
from .utils import get_latest_query

logger = logging.getLogger(__name__)


def continue_after_guardrail(state: AgentState, runtime: Runtime[Context]) -> Literal["continue", "out_of_scope"]:
    """Determine whether to continue or reject based on guardrail results.

    :param state: Current agent state with guardrail results
    :param runtime: Runtime context containing guardrail threshold
    :returns: "continue" if score >= threshold, "out_of_scope" otherwise
    """
    guardrail_result = state.get("guardrail_result")
    if not guardrail_result:
        logger.warning("No guardrail result found, defaulting to continue")
        return "continue"

    score = guardrail_result.score
    threshold = runtime.context.guardrail_threshold

    logger.info(f"Guardrail score: {score}, threshold: {threshold}")
    return "continue" if score >= threshold else "out_of_scope"


@logfire.instrument("node:guardrail", extract_args=False)
async def ainvoke_guardrail_step(
    state: AgentState,
    runtime: Runtime[Context],
) -> Dict[str, GuardrailScoring]:
    """Asynchronously invoke the guardrail validation step.

    Uses AWS Bedrock Guardrails when guardrails_service is configured.
    Falls back to fail-open (allow all) when Bedrock is not configured.
    Guardrail result is mapped to GuardrailScoring for state compatibility:
      - allowed → score=100
      - blocked → score=0

    :param state: Current agent state
    :param runtime: Runtime context
    :returns: Dictionary with guardrail_result
    """
    logger.info("NODE: guardrail_validation")
    start_time = time.time()

    query = get_latest_query(state["messages"])
    logger.debug(f"Evaluating query: {query[:100]}...")

    span = None
    if runtime.context.langfuse_enabled and runtime.context.trace:
        try:
            span = runtime.context.langfuse_tracer.create_span(
                trace=runtime.context.trace,
                name="guardrail_validation",
                input_data={
                    "query": query,
                    "threshold": runtime.context.guardrail_threshold,
                    "guardrails_provider": "bedrock" if runtime.context.guardrails_service else "none",
                },
                metadata={"node": "guardrail"},
            )
        except Exception as e:
            logger.warning(f"Failed to create Langfuse span for guardrail: {e}")

    try:
        if runtime.context.guardrails_service:
            result = await runtime.context.guardrails_service.check_input(query)
            score = 100 if result.allowed else 0
            reason = result.reason
            logger.info(f"Bedrock guardrail: action={result.action}, allowed={result.allowed}, reason={reason}")
        else:
            # No guardrails configured — fail-open
            score = 100
            reason = "No guardrail service configured — passing through"
            logger.debug(reason)

        response = GuardrailScoring(score=score, reason=reason)

        if span:
            execution_time = (time.time() - start_time) * 1000
            runtime.context.langfuse_tracer.end_span(
                span,
                output={
                    "score": response.score,
                    "reason": response.reason,
                    "decision": "continue" if response.score >= runtime.context.guardrail_threshold else "out_of_scope",
                },
                metadata={"execution_time_ms": execution_time},
            )

    except Exception as e:
        logger.error(f"Guardrail validation failed: {e}, falling back to allow")
        response = GuardrailScoring(
            score=100,
            reason=f"Guardrail check failed (fail-open): {str(e)}",
        )
        if span:
            execution_time = (time.time() - start_time) * 1000
            runtime.context.langfuse_tracer.update_span(
                span,
                output={"score": response.score, "reason": response.reason, "error": str(e)},
                metadata={"execution_time_ms": execution_time, "fallback": True},
                level="WARNING",
            )
            runtime.context.langfuse_tracer.end_span(span)

    return {"guardrail_result": response}
