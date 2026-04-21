from typing import Annotated, Any, Dict, List, Optional, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages

from .models import GradingResult, GuardrailScoring, RoutingDecision, SourceItem, ToolArtefact


class AgentState(TypedDict):
    """State class for the Agentic RAG workflow.

    TypedDict-based state following LangGraph 2025 best practices.
    Tracks all data that needs to be passed between nodes.

    :cvar messages:
        List of messages in the conversation. Uses add_messages reducer
        to append new messages rather than overwrite.
    :type messages: Annotated[list[AnyMessage], add_messages]

    :cvar original_query:
        The original user query before any rewrites.
    :type original_query: Optional[str]

    :cvar rewritten_query:
        The rewritten query after optimization for better retrieval.
    :type rewritten_query: Optional[str]

    :cvar retrieval_attempts:
        Number of retrieval attempts made (for max attempt tracking).
    :type retrieval_attempts: int

    :cvar guardrail_result:
        Result from guardrail validation with score and reasoning.
    :type guardrail_result: Optional[GuardrailScoring]

    :cvar routing_decision:
        The routing decision determining the next node in the graph.
    :type routing_decision: Optional[RoutingDecision]

    :cvar sources:
        Dictionary mapping tool_call_id to their output sources.
    :type sources: Optional[Dict[str, Any]]

    :cvar relevant_sources:
        List of relevant sources to display to the user.
    :type relevant_sources: List[SourceItem]

    :cvar relevant_tool_artefacts:
        List of tool artifacts with metadata from tool executions.
    :type relevant_tool_artefacts: Optional[List[ToolArtefact]]

    :cvar grading_results:
        List of grading results for each retrieved document.
    :type grading_results: List[GradingResult]

    :cvar metadata:
        Runtime metadata for tracing and analytics.
    :type metadata: Dict[str, Any]
    """

    messages: Annotated[list[AnyMessage], add_messages]
    original_query: Optional[str]
    rewritten_query: Optional[str]
    retrieval_attempts: int
    guardrail_result: Optional[GuardrailScoring]
    routing_decision: Optional[RoutingDecision]
    sources: Optional[Dict[str, Any]]
    relevant_sources: List[SourceItem]
    relevant_tool_artefacts: Optional[List[ToolArtefact]]
    grading_results: List[GradingResult]
    metadata: Dict[str, Any]
