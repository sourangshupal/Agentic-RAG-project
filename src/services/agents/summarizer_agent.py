from __future__ import annotations

import logging
from dataclasses import dataclass

from src.services.agents.context import Context

logger = logging.getLogger(__name__)


@dataclass
class SummaryResult:
    summary: str
    topic: str
    chunks_used: int


class SummarizerAgent:
    """Minimal summarizer: search topic → ask LLM to summarize results."""

    def __init__(self, context: Context) -> None:
        self._ctx = context

    async def summarize(self, topic: str) -> SummaryResult:
        logger.info("SummarizerAgent: summarizing topic=%s", topic)

        # Reuse existing opensearch client for text search
        results = self._ctx.opensearch_client.search_unified(
            query=topic,
            size=5,
            use_hybrid=False,
        )
        hits = results.get("hits", [])
        chunks = [hit.get("text", "") for hit in hits]
        chunks = [c for c in chunks if c]

        if not chunks:
            return SummaryResult(
                summary=f"No papers found about '{topic}'.",
                topic=topic,
                chunks_used=0,
            )

        context_text = "\n\n".join(chunks[:5])
        prompt = (
            f"Summarize the following research excerpts about '{topic}' in 3-5 sentences:\n\n"
            f"{context_text}"
        )

        # Reuse existing LLM client
        llm_result = await self._ctx.llm_client.generate_rag_answer(
            query=prompt,
            chunks=chunks,
            model=self._ctx.model_name,
        )
        summary = llm_result.get("answer", "")

        return SummaryResult(
            summary=summary,
            topic=topic,
            chunks_used=len(chunks),
        )
