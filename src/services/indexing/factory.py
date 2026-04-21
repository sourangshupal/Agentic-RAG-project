from typing import Optional

from src.config import Settings, get_settings
from src.services.embeddings.factory import make_embeddings_client
from src.services.opensearch.factory import make_opensearch_client_fresh

from .hybrid_indexer import HybridIndexingService
from .text_chunker import TextChunker


def make_hybrid_indexing_service(
    settings: Optional[Settings] = None, opensearch_host: Optional[str] = None
) -> HybridIndexingService:
    """Factory function to create hybrid indexing service.

    Creates a new service instance each time.

    :param settings: Optional settings instance
    :param opensearch_host: Optional OpenSearch host override
    :returns: HybridIndexingService instance
    """
    if settings is None:
        settings = get_settings()

    # Create dependencies using configuration
    chunker = TextChunker(
        chunk_size=settings.chunking.chunk_size,
        overlap_size=settings.chunking.overlap_size,
        min_chunk_size=settings.chunking.min_chunk_size,
    )
    embeddings_client = make_embeddings_client(settings)
    opensearch_client = make_opensearch_client_fresh(settings, host=opensearch_host)

    # Create indexing service
    return HybridIndexingService(chunker=chunker, embeddings_client=embeddings_client, opensearch_client=opensearch_client)
