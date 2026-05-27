from typing import Any, List, Optional

from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    """Request model for RAG question answering."""

    query: str = Field(..., description="User's question", min_length=1, max_length=1000)
    top_k: int = Field(3, description="Number of top chunks to retrieve", ge=1, le=10)
    use_hybrid: bool = Field(True, description="Use hybrid search (BM25 + vector)")
    model: Optional[str] = Field(None, description="Model ID for generation (provider-specific; omit to use server-configured default)")
    categories: Optional[List[str]] = Field(None, description="Filter by arXiv categories")

    class Config:
        json_schema_extra = {
            "example": {
                "query": "What are transformers in machine learning?",
                "top_k": 3,
                "use_hybrid": True,
                "categories": ["cs.AI", "cs.LG"],
            }
        }


class AskResponse(BaseModel):
    """Response model for RAG question answering."""

    query: str = Field(..., description="Original user question")
    answer: str = Field(..., description="Generated answer from LLM")
    sources: List[str] = Field(..., description="PDF URLs of source papers")
    chunks_used: int = Field(..., description="Number of chunks used for generation")
    search_mode: str = Field(..., description="Search mode used: bm25 or hybrid")

    class Config:
        json_schema_extra = {
            "example": {
                "query": "What are transformers in machine learning?",
                "answer": "Transformers are a neural network architecture...",
                "sources": ["https://arxiv.org/pdf/1706.03762.pdf", "https://arxiv.org/pdf/1810.04805.pdf"],
                "chunks_used": 3,
                "search_mode": "hybrid",
                "model": "gpt-4o-mini",
            }
        }


class AgenticAskResponse(AskResponse):
    """Response model for agentic RAG question answering."""

    # Override: agentic endpoint returns rich source objects (arxiv_id, title, authors, url, score)
    sources: List[Any] = Field(..., description="Source papers with metadata")
    reasoning_steps: List[str] = Field(..., description="Agent's decision-making steps")
    retrieval_attempts: int = Field(..., description="Number of document retrieval attempts")
    rewritten_query: Optional[str] = Field(None, description="Rewritten query if agent refined it")
    trace_id: Optional[str] = Field(None, description="Langfuse trace ID for feedback and debugging")
    guardrail_filter: Optional[str] = Field(None, description="Guardrail filter type that acted on this request (e.g. topic_blocked, content_blocked:HATE, pii_blocked:EMAIL, pii_anonymized:PHONE, passed)")
    output_guardrail_filter: Optional[str] = Field(None, description="Output guardrail result — grounding/relevance check on generated answer (e.g. grounding_blocked:grounding score=0.49, or Content passed all guardrail checks)")

    class Config:
        json_schema_extra = {
            "example": {
                "query": "What are transformers in machine learning?",
                "answer": "Transformers are neural network architectures...",
                "sources": [
                    {
                        "arxiv_id": "1706.03762",
                        "title": "Attention Is All You Need",
                        "authors": ["Vaswani et al."],
                        "url": "https://arxiv.org/pdf/1706.03762.pdf",
                        "relevance_score": 0.95,
                    }
                ],
                "chunks_used": 3,
                "search_mode": "hybrid",
                "reasoning_steps": [
                    "Validated query scope (score: 100/100)",
                    "Retrieved documents (1 attempt(s))",
                    "Graded documents (1 relevant)",
                    "Generated answer from context",
                ],
                "retrieval_attempts": 1,
                "rewritten_query": None,
                "trace_id": "019e68a0f28eb4c5579131473f86ca31",
                "guardrail_filter": "Content passed all guardrail checks",
                "output_guardrail_filter": "Content passed all guardrail checks",
            }
        }


class FeedbackRequest(BaseModel):
    """Request model for user feedback on RAG answers."""

    trace_id: str = Field(..., description="Langfuse trace ID from the response")
    score: float = Field(..., description="Feedback score (0-1 or -1 to 1)", ge=-1, le=1)
    comment: Optional[str] = Field(None, description="Optional feedback comment", max_length=1000)

    class Config:
        json_schema_extra = {
            "example": {
                "trace_id": "abc123-def456-ghi789",
                "score": 1.0,
                "comment": "This answer was very helpful and accurate!",
            }
        }


class FeedbackResponse(BaseModel):
    """Response model for feedback submission."""

    success: bool = Field(..., description="Whether feedback was recorded successfully")
    message: str = Field(..., description="Status message")

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "message": "Feedback recorded successfully",
            }
        }
