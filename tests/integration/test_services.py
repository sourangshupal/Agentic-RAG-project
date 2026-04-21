import pytest
from src.config import get_settings
from src.services.arxiv.factory import make_arxiv_client
from src.services.opensearch.factory import make_opensearch_client


async def test_arxiv_client_basic():
    client = make_arxiv_client()

    papers = await client.fetch_papers_with_query("cat:cs.AI", max_results=1)

    assert isinstance(papers, list)


def test_opensearch_client_health():
    client = make_opensearch_client()

    health = client.health_check()
    assert isinstance(health, bool)


def test_settings_loading():
    settings = get_settings()

    assert hasattr(settings, "app_version")
    assert hasattr(settings, "service_name")
    assert hasattr(settings, "environment")
