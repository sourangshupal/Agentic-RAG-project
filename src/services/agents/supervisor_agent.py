from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Literal

from src.services.agents.context import Context
from src.services.agents.summarizer_agent import SummarizerAgent, SummaryResult

logger = logging.getLogger(__name__)

IntentType = Literal["rag_lookup", "summarize"]

INTENT_PROMPT = """You are a router. Classify the user query intent as exactly one word.

Respond with ONLY one of:
- "summarize" — if the user wants a summary or overview of a topic/paper/area
- "rag_lookup" — if the user wants a specific answer, explanation, or comparison

Query: {query}

Intent:"""


@dataclass
class SupervisorResult:
    answer: str
    intent: IntentType
    routed_to: str
    sources: list = field(default_factory=list)


class SupervisorAgent:
    """Routes queries to RAG agent or Summarizer agent based on LLM intent classification."""

    def __init__(self, context: Context, agentic_rag_service) -> None:
        self._ctx = context
        self._rag_agent = agentic_rag_service
        self._summarizer = SummarizerAgent(context)

    async def _classify_intent(self, query: str) -> IntentType:
        prompt = INTENT_PROMPT.format(query=query)
        raw = await self._ctx.llm_client.generate_rag_answer(
            query=prompt,
            chunks=[],
            model=self._ctx.model_name,
        )
        intent_raw = raw.get("answer", "").strip().lower().strip('"').strip("'")
        if "summarize" in intent_raw:
            return "summarize"
        return "rag_lookup"

    async def ask(self, query: str) -> SupervisorResult:
        intent = await self._classify_intent(query)
        logger.info("SupervisorAgent: query routed to intent=%s", intent)

        if intent == "summarize":
            result: SummaryResult = await self._summarizer.summarize(topic=query)
            return SupervisorResult(
                answer=result.summary,
                intent=intent,
                routed_to="SummarizerAgent",
            )

        # Default: delegate to existing RAG agent
        rag_result = await self._rag_agent.ask(query=query)
        return SupervisorResult(
            answer=rag_result["answer"],
            intent=intent,
            routed_to="AgenticRAGService",
            sources=rag_result.get("sources", []),
        )
