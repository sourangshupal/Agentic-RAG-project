import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional

from .common import get_cached_services

logger = logging.getLogger(__name__)


async def run_paper_ingestion_pipeline(
    target_date: str,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    process_pdfs: bool = True,
) -> dict:
    """Async wrapper for the paper ingestion pipeline.

    :param target_date: Date to fetch papers for (YYYYMMDD format)
    :param from_date: Start date for the fetch window (defaults to target_date)
    :param to_date: End date for the fetch window (defaults to target_date)
    :param process_pdfs: Whether to download and process PDFs
    :returns: Dictionary with ingestion statistics
    """
    arxiv_client, _, database, metadata_fetcher, _ = get_cached_services()

    max_results = arxiv_client.max_results
    logger.info(f"Using default max_results from config: {max_results}")

    # Use 7-day lookback window if from_date/to_date are not explicitly set
    from_dt = from_date or target_date
    to_dt = to_date or target_date

    # Override to a higher limit for the demo to guarantee we get papers
    demo_max_results = 2
    logger.info(f"Overriding max_results to {demo_max_results} for demo ingestion")

    with database.get_session() as session:
        return await metadata_fetcher.fetch_and_process_papers(
            max_results=demo_max_results,
            from_date=from_dt,
            to_date=to_dt,
            process_pdfs=process_pdfs,
            store_to_db=True,
            db_session=session,
        )


def fetch_daily_papers(**context):
    """Fetch daily papers from arXiv and store in PostgreSQL.

    This task:
    1. Determines a 7-day lookback window (from 7 days ago to yesterday)
    2. Fetches papers from arXiv API across the entire window
    3. Downloads and processes PDFs using Docling
    4. Stores metadata and parsed content in PostgreSQL

    Note: OpenSearch indexing is handled by a separate dedicated task
    """
    logger.info("Starting daily paper fetching task")

    execution_date = context.get("execution_date")
    if execution_date:
        to_dt = execution_date - timedelta(days=1)
    else:
        to_dt = datetime.now() - timedelta(days=1)

    # 14-day lookback window: fetch papers from the last 14 days to guarantee results
    from_dt = to_dt - timedelta(days=13)
    from_date = from_dt.strftime("%Y%m%d")
    to_date = to_dt.strftime("%Y%m%d")
    target_date = to_date  # kept for backward XCom compatibility

    logger.info(f"Fetching papers from {from_date} to {to_date} (14-day window)")

    results = asyncio.run(
        run_paper_ingestion_pipeline(
            target_date=target_date,
            from_date=from_date,
            to_date=to_date,
            process_pdfs=True,
        )
    )

    logger.info(f"Fetch complete: {results['papers_fetched']} papers from {from_date} to {to_date} (14-day window)")

    results["date"] = target_date
    results["from_date"] = from_date
    results["to_date"] = to_date
    ti = context.get("ti")
    if ti:
        ti.xcom_push(key="fetch_results", value=results)

    return results
