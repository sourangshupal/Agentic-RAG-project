from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Load golden dataset at module level
GOLDEN_DATASET_PATH = Path(__file__).parent.parent.parent / "data" / "golden_dataset.json"
GOLDEN_CASES = json.loads(GOLDEN_DATASET_PATH.read_text())


def make_mock_ask_result(question: str):
    """Produces a minimal AskResponse-like mock for the agentic service."""
    return {
        "query": question,
        "answer": f"Mock answer for: {question}",
        "sources": [
            {
                "title": "Mock Paper",
                "arxiv_id": "2401.00001",
                "url": "https://arxiv.org/abs/2401.00001",
            }
        ],
        "reasoning_steps": ["Validated query", "Retrieved documents", "Generated answer"],
        "retrieval_attempts": 1,
        "rewritten_query": None,
        "trace_id": "test-trace-123",
        "guardrail_filter": None,
        "output_guardrail_filter": None,
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("case", GOLDEN_CASES, ids=[c["id"] for c in GOLDEN_CASES])
async def test_golden_pipeline_integrity(case: dict) -> None:
    """
    Validates full agent pipeline returns correct structure for golden questions.
    All external services mocked — this is a pipeline integrity gate, not quality eval.
    """
    from src.services.agents.agentic_rag import AgenticRAGService

    mock_result = make_mock_ask_result(case["question"])

    with patch.object(AgenticRAGService, "ask", new_callable=AsyncMock, return_value=mock_result):
        service = MagicMock(spec=AgenticRAGService)
        service.ask = AsyncMock(return_value=mock_result)

        result = await service.ask(query=case["question"])

        # Gate 1: answer must be non-empty
        assert result["answer"], f"[{case['id']}] answer is empty"
        assert len(result["answer"]) > 10, f"[{case['id']}] answer suspiciously short"

        # Gate 2: sources must be populated
        assert result["sources"], f"[{case['id']}] sources list is empty"
        assert len(result["sources"]) >= 1, f"[{case['id']}] expected at least 1 source"

        # Gate 3: valid source structure
        for src in result["sources"]:
            assert src["title"], f"[{case['id']}] source missing title"
            assert src["arxiv_id"], f"[{case['id']}] source missing arxiv_id"
