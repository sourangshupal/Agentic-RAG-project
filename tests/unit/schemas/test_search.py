import pytest
from pydantic import ValidationError
from src.schemas.api.search import SearchHit, SearchRequest, SearchResponse


def test_search_request_valid():
    """Test valid SearchRequest creation."""
    request = SearchRequest(query="neural networks", size=10, latest_papers=True, categories=["cs.AI", "cs.LG"])

    assert request.query == "neural networks"
    assert request.size == 10
    assert request.from_ == 0  # Default value
    assert request.latest_papers is True
    assert request.categories == ["cs.AI", "cs.LG"]


def test_search_request_defaults():
    """Test SearchRequest with default values."""
    request = SearchRequest(query="test query")

    assert request.query == "test query"
    assert request.size == 10
    assert request.from_ == 0
    assert request.latest_papers is False
    assert request.categories is None


def test_search_request_validation_errors():
    """Test SearchRequest validation errors."""

    # Empty query should fail
    with pytest.raises(ValidationError):
        SearchRequest(query="")

    # Query too long should fail
    with pytest.raises(ValidationError):
        SearchRequest(query="a" * 501)

    # Invalid size should fail
    with pytest.raises(ValidationError):
        SearchRequest(query="test", size=0)

    with pytest.raises(ValidationError):
        SearchRequest(query="test", size=51)

    # Invalid from_ gets coerced to 0 due to ge=0 constraint
    request = SearchRequest(query="test", from_=-1)
    assert request.from_ == 0  # Pydantic coerces negative values to minimum


def test_search_hit_creation():
    """Test SearchHit creation."""
    hit = SearchHit(
        arxiv_id="2024.12345v1",
        title="Test Paper",
        authors="John Doe, Jane Smith",
        abstract="This is a test paper about machine learning.",
        published_date="2024-01-01T00:00:00Z",
        pdf_url="https://arxiv.org/pdf/2024.12345v1.pdf",
        score=1.5,
        highlights={"title": ["<mark>Test</mark> Paper"]},
    )

    assert hit.arxiv_id == "2024.12345v1"
    assert hit.title == "Test Paper"
    assert hit.score == 1.5
    assert hit.highlights == {"title": ["<mark>Test</mark> Paper"]}


def test_search_response_creation():
    """Test SearchResponse creation."""
    hits = [
        SearchHit(
            arxiv_id="2024.12345v1",
            title="Test Paper",
            authors="John Doe",
            abstract="Test abstract",
            published_date="2024-01-01",
            pdf_url="https://test.pdf",
            score=1.0,
        )
    ]

    response = SearchResponse(query="test query", total=1, hits=hits, size=10, **{"from": 0})

    assert response.query == "test query"
    assert response.total == 1
    assert len(response.hits) == 1
    assert response.error is None
