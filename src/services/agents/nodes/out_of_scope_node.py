import logging
from typing import Dict, List

from langchain_core.messages import AIMessage
from langgraph.runtime import Runtime

from ..context import Context
from ..state import AgentState
from .utils import get_latest_query

logger = logging.getLogger(__name__)


async def ainvoke_out_of_scope_step(
    state: AgentState,
    runtime: Runtime[Context],
) -> Dict[str, List[AIMessage]]:
    """Handle out-of-scope queries with a helpful message.

    This node responds to queries that are outside the domain of
    CS/AI/ML research papers with a polite, informative message.

    :param state: Current agent state
    :param runtime: Runtime context (not used in this node)
    :returns: Dictionary with messages containing the out-of-scope response
    """
    logger.info("NODE: out_of_scope")

    question = get_latest_query(state["messages"])

    # Generate helpful response message
    response_text = (
        "I apologize, but I can only help with questions about academic research papers "
        "in Computer Science, Artificial Intelligence, and Machine Learning from arXiv.\n\n"
        f"Your question: '{question}'\n\n"
        "This appears to be outside my domain of expertise. For questions like this, you might want to try:\n"
        "- General-purpose AI assistants for broad knowledge questions\n"
        "- Domain-specific resources for topics outside CS/AI/ML\n"
        "- Technical documentation if asking about specific software/tools\n\n"
        "If you have a question about AI/ML research papers, I'd be happy to help!"
    )

    logger.info("Responding with out-of-scope message")

    return {"messages": [AIMessage(content=response_text)]}
