"""Simple, efficient Langfuse tracing utility for RAG pipeline."""

import time
from contextlib import contextmanager
from typing import Any, Dict, List, Optional

from .client import LangfuseTracer


class RAGTracer:
    """Clean, purpose-built tracer for RAG operations."""

    def __init__(self, tracer: LangfuseTracer):
        self.tracer = tracer

    @contextmanager
    def trace_request(self, user_id: str, query: str):
        """Main request trace context manager."""
        try:
            with self.tracer.start_span(
                name="rag_request",
                input_data={"query": query, "user_id": user_id},
                metadata={"simplified_tracing": True},
            ) as trace:
                yield trace
        finally:
            self.tracer.flush()

    @contextmanager
    def trace_embedding(self, trace, query: str):
        """Query embedding operation with timing."""
        start_time = time.time()
        with self.tracer.start_span(
            name="query_embedding",
            input_data={"query": query, "query_length": len(query)},
        ) as span:
            try:
                yield span
            finally:
                duration = time.time() - start_time
                if span:
                    self.tracer.update_span(
                        span=span,
                        output={"embedding_duration_ms": round(duration * 1000, 2), "success": True},
                    )

    @contextmanager
    def trace_search(self, trace, query: str, top_k: int):
        """Search operation with timing."""
        with self.tracer.start_span(
            name="search_retrieval",
            input_data={"query": query, "top_k": top_k},
        ) as span:
            yield span

    def end_search(self, span, chunks: List[Dict], arxiv_ids: List[str], total_hits: int):
        """End search span with essential results."""
        if not span:
            return

        self.tracer.update_span(
            span=span,
            output={
                "chunks_returned": len(chunks),
                "unique_papers": len(set(arxiv_ids)),
                "total_hits": total_hits,
                "arxiv_ids": list(set(arxiv_ids)),
            },
        )

    @contextmanager
    def trace_prompt_construction(self, trace, chunks: List[Dict]):
        """Prompt building with timing."""
        with self.tracer.start_span(
            name="prompt_construction",
            input_data={"chunk_count": len(chunks)},
        ) as span:
            yield span

    def end_prompt(self, span, prompt: str):
        """End prompt span with final prompt."""
        if not span:
            return

        self.tracer.update_span(
            span=span,
            output={
                "prompt_length": len(prompt),
                "prompt_preview": prompt[:200] + "..." if len(prompt) > 200 else prompt,
            },
        )

    @contextmanager
    def trace_generation(self, trace, model: str, prompt: str):
        """LLM generation with timing."""
        with self.tracer.start_span(
            name="llm_generation",
            input_data={"model": model, "prompt_length": len(prompt), "prompt": prompt},
        ) as span:
            yield span

    def end_generation(self, span, response: str, model: str):
        """End generation span with response."""
        if not span:
            return

        self.tracer.update_span(span=span, output={"response": response, "response_length": len(response), "model_used": model})

    def end_request(self, trace, response: str, total_duration: float):
        """End main request trace."""
        if not trace:
            return

        try:
            trace.update(
                output={"answer": response, "total_duration_seconds": round(total_duration, 3), "response_length": len(response)}
            )
        except Exception:
            pass
