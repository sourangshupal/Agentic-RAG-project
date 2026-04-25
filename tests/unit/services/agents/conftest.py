"""Shared fixtures for agent unit tests."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from src.services.agents.context import Context


@pytest.fixture
def mock_opensearch_client():
    client = MagicMock()
    client.search_unified = MagicMock(return_value={"hits": [], "total": 0})
    return client


class _MockRewriteOutput:
    rewritten_query = "What are the key transformer architectures for NLP tasks?"
    reasoning = "Added technical specificity for better retrieval"


@pytest.fixture
def mock_llm_client():
    client = MagicMock()
    mock_chat_model = MagicMock()
    # For plain ainvoke (generate_answer, grade_documents nodes)
    mock_chat_model.ainvoke = AsyncMock(return_value=MagicMock(content="Mock answer"))
    # For structured output (guardrail, rewrite nodes) — return a real-looking object
    mock_structured = MagicMock()
    mock_structured.ainvoke = AsyncMock(return_value=_MockRewriteOutput())
    mock_chat_model.with_structured_output = MagicMock(return_value=mock_structured)
    client.get_langchain_model = MagicMock(return_value=mock_chat_model)
    return client


@pytest.fixture
def mock_jina_embeddings_client():
    client = MagicMock()
    client.embed_query = AsyncMock(return_value=[0.1] * 1024)
    return client


@pytest.fixture
def test_context(mock_opensearch_client, mock_llm_client, mock_jina_embeddings_client):
    return Context(
        llm_client=mock_llm_client,
        opensearch_client=mock_opensearch_client,
        embeddings_client=mock_jina_embeddings_client,
        langfuse_tracer=None,
        langfuse_enabled=False,
        model_name="gpt-4o-mini",
        temperature=0.0,
        top_k=3,
        max_retrieval_attempts=2,
        guardrail_threshold=60,
    )


@pytest.fixture
def sample_human_message():
    return HumanMessage(content="What is machine learning?")


@pytest.fixture
def sample_ai_message():
    return AIMessage(content="Machine learning is a subset of AI.")


@pytest.fixture
def sample_tool_message():
    return ToolMessage(
        content="Transformers are neural network architectures based on attention mechanisms.",
        tool_call_id="retrieve_papers_call_1",
    )
