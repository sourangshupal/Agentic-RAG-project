"""Insert papers by arXiv ID into PostgreSQL and OpenSearch.

Usage (inside container):
    python scripts/insert_papers_by_id.py 2401.12345 2505.30353

Usage (metadata-only, no PDF download/parse):
    python scripts/insert_papers_by_id.py 2401.12345 --skip-pdf

Usage (replace existing papers in OpenSearch):
    python scripts/insert_papers_by_id.py 2401.12345 --replace-existing

# ── Ingestion commands for the three test papers ──────────────────────────
# Paper 1: 1706.03762  (Attention Is All You Need — Transformer)
# Paper 2: 1512.03385  (Deep Residual Learning for Image Recognition — ResNet)
# Paper 3: 1409.1556   (Very Deep Convolutional Networks for Large-Scale Image Recognition — VGG)
#
# Run inside the Airflow pod:
#   kubectl cp scripts/insert_papers_by_id.py <AIRFLOW_POD>:/tmp/insert_papers_by_id.py -n production
#   kubectl exec <AIRFLOW_POD> -n production -- python /tmp/insert_papers_by_id.py 1706.03762 1512.03385 1409.1556
#
# Retry for failed papers after arXiv rate-limit cooldown:
#   kubectl exec <AIRFLOW_POD> -n production -- python /tmp/insert_papers_by_id.py 1706.03762 1512.03385
#
# Retry single paper:
#   kubectl exec <AIRFLOW_POD> -n production -- python /tmp/insert_papers_by_id.py 1706.03762
#
# Results:
#   1409.1556 (VGG)  → SUCCESS — 25 chunks indexed
#   1706.03762 (Transformer) → FAILED — arXiv API HTTP 429 (rate limited)
#   1512.03385 (ResNet)      → FAILED — arXiv API HTTP 429 (rate limited)
"""
import argparse
import asyncio
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Ensure src/ is importable when running inside either container
sys.path.insert(0, "/app")
sys.path.insert(0, "/opt/airflow")

from dateutil import parser as date_parser
from sqlalchemy.orm import Session

from src.config import get_settings
from src.db.factory import make_database
from src.repositories.paper import PaperRepository
from src.schemas.arxiv.paper import ArxivPaper, PaperCreate
from src.schemas.pdf_parser.models import ArxivMetadata, ParsedPaper, PdfContent
from src.services.arxiv.client import ArxivClient
from src.services.indexing.factory import make_hybrid_indexing_service
from src.services.opensearch.client import OpenSearchClient
from src.services.pdf_parser.parser import PDFParserService

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger(__name__)


def parse_date(published_date: str) -> datetime:
    """Parse arXiv date string to datetime."""
    if isinstance(published_date, datetime):
        return published_date
    try:
        return date_parser.parse(published_date)
    except Exception:
        return datetime.now(timezone.utc)


async def fetch_paper_metadata(arxiv_client: ArxivClient, arxiv_id: str) -> Optional[ArxivPaper]:
    """Fetch paper metadata from arXiv API by ID."""
    logger.info(f"[{arxiv_id}] Fetching metadata from arXiv...")
    try:
        paper = await arxiv_client.fetch_paper_by_id(arxiv_id)
        if paper:
            logger.info(f"[{arxiv_id}] Found: {paper.title[:60]}...")
            return paper
        else:
            logger.error(f"[{arxiv_id}] Not found on arXiv")
            return None
    except Exception as e:
        logger.error(f"[{arxiv_id}] Failed to fetch metadata: {e}")
        return None


async def download_and_parse_pdf(
    arxiv_client: ArxivClient,
    pdf_parser: PDFParserService,
    paper: ArxivPaper,
) -> Tuple[bool, Optional[ParsedPaper]]:
    """Download and parse PDF for a paper.

    Returns:
        Tuple of (download_success, parsed_paper_or_none)
    """
    logger.info(f"[{paper.arxiv_id}] Downloading PDF...")
    try:
        pdf_path = await arxiv_client.download_pdf(paper, force_download=False)
        if not pdf_path:
            logger.warning(f"[{paper.arxiv_id}] PDF download failed")
            return False, None

        logger.info(f"[{paper.arxiv_id}] PDF downloaded: {pdf_path.name}")

        logger.info(f"[{paper.arxiv_id}] Parsing PDF with Docling...")
        pdf_content = await pdf_parser.parse_pdf(pdf_path)

        if pdf_content:
            arxiv_metadata = ArxivMetadata(
                title=paper.title,
                authors=paper.authors,
                abstract=paper.abstract,
                arxiv_id=paper.arxiv_id,
                categories=paper.categories,
                published_date=paper.published_date,
                pdf_url=paper.pdf_url,
            )
            parsed_paper = ParsedPaper(arxiv_metadata=arxiv_metadata, pdf_content=pdf_content)
            logger.info(f"[{paper.arxiv_id}] Parsed: {len(pdf_content.raw_text)} chars, {len(pdf_content.sections)} sections")
            return True, parsed_paper
        else:
            logger.warning(f"[{paper.arxiv_id}] PDF parsing returned no content")
            return True, None

    except Exception as e:
        logger.error(f"[{paper.arxiv_id}] PDF processing error: {e}")
        return False, None


def serialize_parsed_content(parsed_paper: ParsedPaper) -> Dict[str, Any]:
    """Serialize ParsedPaper content for database storage."""
    pdf_content = parsed_paper.pdf_content
    sections = [{"title": section.title, "content": section.content} for section in pdf_content.sections]
    references = list(pdf_content.references) if hasattr(pdf_content, "references") else []

    return {
        "raw_text": pdf_content.raw_text,
        "sections": sections,
        "references": references,
        "parser_used": pdf_content.parser_used.value if pdf_content.parser_used else "DOCLING",
        "parser_metadata": pdf_content.metadata or {},
        "pdf_processed": True,
        "pdf_processing_date": datetime.now(timezone.utc),
    }


def store_paper_to_db(
    db_session: Session,
    paper: ArxivPaper,
    parsed_paper: Optional[ParsedPaper] = None,
) -> Optional[str]:
    """Store paper and parsed content to PostgreSQL.

    Returns:
        Database ID (UUID string) of the stored paper, or None on failure.
    """
    try:
        paper_repo = PaperRepository(db_session)

        published_date = parse_date(paper.published_date)

        paper_data = {
            "arxiv_id": paper.arxiv_id,
            "title": paper.title,
            "authors": paper.authors,
            "abstract": paper.abstract,
            "categories": paper.categories,
            "published_date": published_date,
            "pdf_url": paper.pdf_url,
        }

        if parsed_paper:
            parsed_content = serialize_parsed_content(parsed_paper)
            paper_data.update(parsed_content)
            logger.info(f"[{paper.arxiv_id}] Storing with parsed PDF content")
        else:
            paper_data.update({
                "pdf_processed": False,
                "parser_metadata": {"note": "PDF processing skipped or failed"},
            })
            logger.info(f"[{paper.arxiv_id}] Storing metadata only")

        paper_create = PaperCreate(**paper_data)
        stored_paper = paper_repo.upsert(paper_create)

        db_session.commit()
        paper_id = str(stored_paper.id)
        logger.info(f"[{paper.arxiv_id}] Stored to DB with ID: {paper_id}")
        return paper_id

    except Exception as e:
        logger.error(f"[{paper.arxiv_id}] Database storage failed: {e}")
        db_session.rollback()
        return None


async def index_paper_to_opensearch(
    indexing_service,
    paper: ArxivPaper,
    paper_id: str,
    raw_text: Optional[str] = None,
    sections: Optional[List[Dict[str, Any]]] = None,
    replace_existing: bool = False,
) -> Dict[str, int]:
    """Index a single paper into OpenSearch with chunking and embeddings."""
    paper_data = {
        "id": paper_id,
        "arxiv_id": paper.arxiv_id,
        "title": paper.title,
        "authors": paper.authors,
        "abstract": paper.abstract,
        "categories": paper.categories,
        "published_date": parse_date(paper.published_date).isoformat(),
        "raw_text": raw_text or paper.abstract,  # Fallback to abstract if no raw_text
        "sections": sections or [],
    }

    try:
        stats = await indexing_service.index_paper(paper_data)
        if replace_existing and stats["chunks_indexed"] == 0 and stats["errors"] == 0:
            # Paper might already exist; force re-index
            logger.info(f"[{paper.arxiv_id}] Forcing re-index...")
            stats = await indexing_service.reindex_paper(paper.arxiv_id, paper_data)

        logger.info(
            f"[{paper.arxiv_id}] Indexed: {stats['chunks_indexed']} chunks, "
            f"{stats['embeddings_generated']} embeddings, {stats['errors']} errors"
        )
        return stats
    except Exception as e:
        logger.error(f"[{paper.arxiv_id}] OpenSearch indexing failed: {e}")
        return {"chunks_indexed": 0, "embeddings_generated": 0, "errors": 1}


async def process_single_paper(
    arxiv_id: str,
    arxiv_client: ArxivClient,
    pdf_parser: PDFParserService,
    db_session: Session,
    indexing_service,
    skip_pdf: bool = False,
    replace_existing: bool = False,
) -> Dict[str, Any]:
    """Process a single paper: fetch, parse, store, index.

    Returns a result dict with keys: success, arxiv_id, paper_id, chunks_indexed, error
    """
    result = {
        "success": False,
        "arxiv_id": arxiv_id,
        "paper_id": None,
        "chunks_indexed": 0,
        "error": None,
    }

    # 1. Fetch metadata
    paper = await fetch_paper_metadata(arxiv_client, arxiv_id)
    if not paper:
        result["error"] = "Metadata fetch failed"
        return result

    # 2. Download & parse PDF (optional)
    parsed_paper: Optional[ParsedPaper] = None
    if not skip_pdf:
        _, parsed_paper = await download_and_parse_pdf(arxiv_client, pdf_parser, paper)
    else:
        logger.info(f"[{arxiv_id}] Skipping PDF download (--skip-pdf)")

    # 3. Store to PostgreSQL
    paper_id = store_paper_to_db(
        db_session,
        paper,
        parsed_paper=parsed_paper,
    )
    if not paper_id:
        result["error"] = "Database storage failed"
        return result

    result["paper_id"] = paper_id

    # 4. Index to OpenSearch
    raw_text = parsed_paper.pdf_content.raw_text if parsed_paper else None
    sections = None
    if parsed_paper and parsed_paper.pdf_content.sections:
        sections = [{"title": s.title, "content": s.content} for s in parsed_paper.pdf_content.sections]

    index_stats = await index_paper_to_opensearch(
        indexing_service,
        paper,
        paper_id,
        raw_text=raw_text,
        sections=sections,
        replace_existing=replace_existing,
    )

    result["chunks_indexed"] = index_stats.get("chunks_indexed", 0)
    if index_stats.get("errors", 0) > 0:
        result["error"] = f"Indexing had {index_stats['errors']} errors"
        # Still consider partial success if some chunks were indexed
        if result["chunks_indexed"] > 0:
            result["success"] = True
        return result

    result["success"] = True
    return result


async def main():
    parser = argparse.ArgumentParser(
        description="Insert papers by arXiv ID into PostgreSQL and OpenSearch",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/insert_papers_by_id.py 2401.12345 2505.30353
  python scripts/insert_papers_by_id.py 2401.12345 --skip-pdf
  python scripts/insert_papers_by_id.py 2401.12345 --replace-existing
        """,
    )
    parser.add_argument(
        "arxiv_ids",
        nargs="+",
        help="One or more arXiv paper IDs (e.g., 2401.12345 or 2401.12345v1)",
    )
    parser.add_argument(
        "--skip-pdf",
        action="store_true",
        help="Skip PDF download and parsing. Only store metadata + abstract. Faster but less content for search.",
    )
    parser.add_argument(
        "--replace-existing",
        action="store_true",
        help="Replace existing paper chunks in OpenSearch if paper already exists.",
    )
    parser.add_argument(
        "--opensearch-host",
        default=None,
        help="Override OpenSearch host (default: from env/config)",
    )
    parser.add_argument(
        "--pdf-cache-dir",
        default="/tmp/arxiv_pdfs",
        help="Directory to cache downloaded PDFs",
    )

    args = parser.parse_args()

    # Clean arXiv IDs (strip version suffixes for consistency)
    arxiv_ids = [aid.split("v")[0] for aid in args.arxiv_ids]
    logger.info(f"Starting ingestion for {len(arxiv_ids)} paper(s): {arxiv_ids}")

    # Initialize settings and services
    settings = get_settings()

    # Create arXiv client
    arxiv_client = ArxivClient(settings=settings.arxiv)

    # Create PDF parser (only needed if not skipping)
    pdf_parser = None
    if not args.skip_pdf:
        pdf_parser = PDFParserService(
            max_pages=settings.pdf_parser.max_pages,
            max_file_size_mb=settings.pdf_parser.max_file_size_mb,
            do_ocr=settings.pdf_parser.do_ocr,
            do_table_structure=settings.pdf_parser.do_table_structure,
        )

    # Create database connection
    database = make_database()

    # Create indexing service
    indexing_service = make_hybrid_indexing_service(
        settings=settings,
        opensearch_host=args.opensearch_host,
    )
    indexing_service.opensearch_client.setup_indices()

    # Process each paper
    results: List[Dict[str, Any]] = []

    with database.get_session() as db_session:
        for arxiv_id in arxiv_ids:
            logger.info(f"\n{'='*60}")
            logger.info(f"Processing paper: {arxiv_id}")
            logger.info(f"{'='*60}")

            result = await process_single_paper(
                arxiv_id=arxiv_id,
                arxiv_client=arxiv_client,
                pdf_parser=pdf_parser,
                db_session=db_session,
                indexing_service=indexing_service,
                skip_pdf=args.skip_pdf,
                replace_existing=args.replace_existing,
            )
            results.append(result)

    # Final summary
    successful = [r for r in results if r["success"]]
    failed = [r for r in results if not r["success"]]
    total_chunks = sum(r["chunks_indexed"] for r in results)

    logger.info(f"\n{'='*60}")
    logger.info(f"INGESTION SUMMARY")
    logger.info(f"{'='*60}")
    logger.info(f"Papers requested:    {len(arxiv_ids)}")
    logger.info(f"Successful:          {len(successful)}")
    logger.info(f"Failed:              {len(failed)}")
    logger.info(f"Total chunks indexed: {total_chunks}")

    if failed:
        logger.info(f"\nFailed papers:")
        for r in failed:
            logger.info(f"  - {r['arxiv_id']}: {r['error']}")

    if successful:
        logger.info(f"\nSuccessful papers:")
        for r in successful:
            logger.info(f"  - {r['arxiv_id']}: {r['chunks_indexed']} chunks indexed")

    # Verify OpenSearch index
    try:
        stats = indexing_service.opensearch_client.get_index_stats()
        logger.info(f"\nOpenSearch index: {stats.get('index_name')}")
        logger.info(f"Total documents:    {stats.get('document_count', 0)}")
    except Exception as e:
        logger.warning(f"Could not get OpenSearch stats: {e}")

    # Exit with error code if any failed
    sys.exit(0 if len(failed) == 0 else 1)


if __name__ == "__main__":
    asyncio.run(main())
