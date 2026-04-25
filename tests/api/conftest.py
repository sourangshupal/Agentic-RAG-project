from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient
from src.main import app


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    """Async backend for testing."""
    return "asyncio"


@pytest.fixture
async def client():
    """HTTP client for API testing with all external services mocked."""
    mock_db = MagicMock()
    mock_db.startup.return_value = None
    mock_db.teardown.return_value = None
    mock_db.get_session.return_value.__enter__ = MagicMock(return_value=MagicMock())
    mock_db.get_session.return_value.__exit__ = MagicMock(return_value=None)

    mock_opensearch = MagicMock()
    mock_opensearch.health_check.return_value = True
    mock_opensearch.setup_indices.return_value = {"hybrid_index": False}
    mock_opensearch.index_name = "arxiv-papers-chunks"
    mock_opensearch.client.count.return_value = {"count": 42}
    mock_opensearch.search_unified.return_value = {"hits": [], "total": 0}

    # Patch at src.main.* — where the names are bound after import
    with (
        patch("src.main.make_database", return_value=mock_db),
        patch("src.main.make_opensearch_client", return_value=mock_opensearch),
        patch("src.main.make_arxiv_client", return_value=AsyncMock()),
        patch("src.main.make_pdf_parser_service", return_value=AsyncMock()),
        patch("src.main.make_embeddings_service", return_value=MagicMock()),
        patch("src.main.make_openai_llm_client", return_value=MagicMock()),
        patch("src.main.make_langfuse_tracer", return_value=None),
        patch("src.main.make_cache_client", return_value=MagicMock()),
        patch("src.main.make_telegram_service", return_value=None),
    ):
        async with LifespanManager(app) as manager:
            async with AsyncClient(
                transport=ASGITransport(app=manager.app), base_url="http://test"
            ) as client:
                yield client
