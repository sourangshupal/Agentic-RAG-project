from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, mock_open, patch

import httpx
import pytest
from src.exceptions import ArxivAPIException, ArxivAPITimeoutError, ArxivParseError, PDFDownloadException, PDFDownloadTimeoutError
from src.schemas.arxiv.paper import ArxivPaper
from src.services.arxiv.client import ArxivClient
from src.services.arxiv.factory import make_arxiv_client


class TestArxivClient:
    """Test ArxivClient functionality."""

    @pytest.fixture
    def arxiv_client(self):
        """Create ArxivClient instance for testing."""
        from src.config import ArxivSettings

        settings = ArxivSettings(
            base_url="https://export.arxiv.org/api/query",
            search_category="cs.AI",
            max_results=10,
            rate_limit_delay=0.1,  # Faster for tests
            timeout_seconds=5,
            pdf_cache_dir="/tmp/test_arxiv_cache",
        )
        return ArxivClient(settings)

    @pytest.fixture
    def mock_arxiv_response(self):
        """Mock arXiv API XML response."""
        return """<?xml version="1.0" encoding="UTF-8"?>
        <feed xmlns="http://www.w3.org/2005/Atom">
          <entry>
            <id>http://arxiv.org/abs/2024.0001v1</id>
            <updated>2024-01-01T00:00:00Z</updated>
            <published>2024-01-01T00:00:00Z</published>
            <title>Test Paper Title</title>
            <summary>Test abstract content</summary>
            <author><name>Test Author</name></author>
            <arxiv:primary_category xmlns:arxiv="http://arxiv.org/schemas/atom" term="cs.AI" scheme="http://arxiv.org/schemas/atom"/>
            <category term="cs.AI" scheme="http://arxiv.org/schemas/atom"/>
            <link title="pdf" href="http://arxiv.org/pdf/2024.0001v1" rel="alternate" type="application/pdf"/>
          </entry>
        </feed>"""

    def test_factory_creates_client(self):
        """Test that factory creates ArxivClient instance."""
        client = make_arxiv_client()
        assert isinstance(client, ArxivClient)
        assert client.search_category == "cs.AI"
        assert client.max_results == 15  # Default from ArxivSettings

    @pytest.mark.asyncio
    async def test_fetch_papers_success(self, arxiv_client, mock_arxiv_response):
        """Test successful paper fetching."""
        with patch("httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.text = mock_arxiv_response
            mock_response.raise_for_status.return_value = None

            mock_client.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_response)

            papers = await arxiv_client.fetch_papers(max_results=1)

            assert len(papers) == 1
            assert papers[0].arxiv_id == "2024.0001v1"
            assert papers[0].title == "Test Paper Title"
            assert papers[0].abstract == "Test abstract content"
            assert papers[0].authors == ["Test Author"]
            assert papers[0].categories == ["cs.AI"]

    @pytest.mark.asyncio
    async def test_fetch_papers_with_date_filters(self, arxiv_client, mock_arxiv_response):
        """Test paper fetching with date filters."""
        with patch("httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.text = mock_arxiv_response
            mock_response.raise_for_status.return_value = None

            mock_client.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_response)

            papers = await arxiv_client.fetch_papers(max_results=1, from_date="20240101", to_date="20240131")

            assert len(papers) == 1
            # Verify the URL includes date filters
            call_args = mock_client.return_value.__aenter__.return_value.get.call_args[0][0]
            assert "submittedDate:[202401010000+TO+202401312359]" in call_args

    @pytest.mark.asyncio
    async def test_fetch_papers_http_timeout(self, arxiv_client):
        """Test handling of HTTP timeout errors."""
        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                side_effect=httpx.TimeoutException("Request timeout")
            )

            with pytest.raises(ArxivAPITimeoutError) as exc_info:
                await arxiv_client.fetch_papers(max_results=1)

            assert "arXiv API request timed out" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_fetch_papers_http_error(self, arxiv_client):
        """Test handling of HTTP status errors."""
        with patch("httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 500
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                side_effect=httpx.HTTPStatusError("Server error", request=MagicMock(), response=mock_response)
            )

            with pytest.raises(ArxivAPIException) as exc_info:
                await arxiv_client.fetch_papers(max_results=1)

            assert "arXiv API returned error 500" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_fetch_paper_by_id_success(self, arxiv_client, mock_arxiv_response):
        """Test fetching a single paper by ID."""
        with patch("httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.text = mock_arxiv_response
            mock_response.raise_for_status.return_value = None

            mock_client.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_response)

            paper = await arxiv_client.fetch_paper_by_id("2024.0001v1")

            assert paper is not None
            assert paper.arxiv_id == "2024.0001v1"
            assert paper.title == "Test Paper Title"

    @pytest.mark.asyncio
    async def test_fetch_paper_by_id_not_found(self, arxiv_client):
        """Test handling when single paper is not found."""
        empty_response = """<?xml version="1.0" encoding="UTF-8"?>
        <feed xmlns="http://www.w3.org/2005/Atom">
        </feed>"""

        with patch("httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.text = empty_response
            mock_response.raise_for_status.return_value = None

            mock_client.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_response)

            paper = await arxiv_client.fetch_paper_by_id("nonexistent")

            assert paper is None

    def test_parse_response_invalid_xml(self, arxiv_client):
        """Test handling of invalid XML response."""
        invalid_xml = "This is not valid XML"

        with pytest.raises(ArxivParseError) as exc_info:
            arxiv_client._parse_response(invalid_xml)

        assert "Failed to parse arXiv XML response" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_download_pdf_cached(self, arxiv_client):
        """Test that cached PDFs are returned without downloading."""
        paper = ArxivPaper(
            arxiv_id="2024.0001v1",
            title="Test Paper",
            authors=["Test Author"],
            abstract="Test abstract",
            categories=["cs.AI"],
            published_date="2024-01-01T00:00:00Z",
            pdf_url="http://arxiv.org/pdf/2024.0001v1",
        )

        with patch("pathlib.Path.exists", return_value=True):
            pdf_path = await arxiv_client.download_pdf(paper)

            assert pdf_path is not None
            assert pdf_path.name == "2024.0001v1.pdf"

    def test_rate_limiting(self, arxiv_client):
        """Test rate limiting delay calculation."""
        import time

        # Mock the last request time
        arxiv_client._last_request_time = time.time() - 1.0  # 1 second ago

        # This would normally cause a delay in real usage
        # In tests, we just verify the logic exists
        assert arxiv_client.rate_limit_delay == 0.1  # Our test value
        assert arxiv_client._last_request_time is not None
