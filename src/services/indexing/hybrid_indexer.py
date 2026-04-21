import logging
from typing import Dict, List, Optional

from src.services.embeddings.jina_client import JinaEmbeddingsClient
from src.services.opensearch.client import OpenSearchClient

from .text_chunker import TextChunker

logger = logging.getLogger(__name__)


class HybridIndexingService:
    """Service for indexing papers with chunking and embeddings for hybrid search.

    Orchestrates the process of:
    1. Chunking papers into overlapping segments
    2. Generating embeddings for each chunk
    3. Indexing chunks with embeddings into OpenSearch
    """

    def __init__(self, chunker: TextChunker, embeddings_client: JinaEmbeddingsClient, opensearch_client: OpenSearchClient):
        """Initialize hybrid indexing service.

        :param chunker: Text chunking service
        :param embeddings_client: Embeddings generation client
        :param opensearch_client: OpenSearch client
        """
        self.chunker = chunker
        self.embeddings_client = embeddings_client
        self.opensearch_client = opensearch_client

        logger.info("Hybrid indexing service initialized")

    async def index_paper(self, paper_data: Dict) -> Dict[str, int]:
        """Index a single paper with chunking and embeddings.

        :param paper_data: Paper data from database
        :returns: Dictionary with indexing statistics
        """
        arxiv_id = paper_data.get("arxiv_id")
        paper_id = str(paper_data.get("id", ""))

        if not arxiv_id:
            logger.error("Paper missing arxiv_id")
            return {"chunks_created": 0, "chunks_indexed": 0, "embeddings_generated": 0, "errors": 1}

        try:
            # Step 1: Chunk the paper using hybrid section-based approach
            chunks = self.chunker.chunk_paper(
                title=paper_data.get("title", ""),
                abstract=paper_data.get("abstract", ""),
                full_text=paper_data.get("raw_text", paper_data.get("full_text", "")),
                arxiv_id=arxiv_id,
                paper_id=paper_id,
                sections=paper_data.get("sections"),
            )

            if not chunks:
                logger.warning(f"No chunks created for paper {arxiv_id}")
                return {"chunks_created": 0, "chunks_indexed": 0, "embeddings_generated": 0, "errors": 0}

            logger.info(f"Created {len(chunks)} chunks for paper {arxiv_id}")

            # Step 2: Generate embeddings for chunks
            chunk_texts = [chunk.text for chunk in chunks]
            embeddings = await self.embeddings_client.embed_passages(
                texts=chunk_texts,
                batch_size=50,  # Process in batches
            )

            if len(embeddings) != len(chunks):
                logger.error(f"Embedding count mismatch: {len(embeddings)} != {len(chunks)}")
                return {"chunks_created": len(chunks), "chunks_indexed": 0, "embeddings_generated": len(embeddings), "errors": 1}

            # Step 3: Prepare chunks with embeddings for indexing
            chunks_with_embeddings = []

            for chunk, embedding in zip(chunks, embeddings):
                # Prepare chunk data for OpenSearch
                chunk_data = {
                    "arxiv_id": chunk.arxiv_id,
                    "paper_id": chunk.paper_id,
                    "chunk_index": chunk.metadata.chunk_index,
                    "chunk_text": chunk.text,
                    "chunk_word_count": chunk.metadata.word_count,
                    "start_char": chunk.metadata.start_char,
                    "end_char": chunk.metadata.end_char,
                    "section_title": chunk.metadata.section_title,
                    "embedding_model": "jina-embeddings-v3",
                    # Denormalized paper metadata for efficient search
                    "title": paper_data.get("title", ""),
                    "authors": ", ".join(paper_data.get("authors", []))
                    if isinstance(paper_data.get("authors"), list)
                    else paper_data.get("authors", ""),
                    "abstract": paper_data.get("abstract", ""),
                    "categories": paper_data.get("categories", []),
                    "published_date": paper_data.get("published_date"),
                }

                chunks_with_embeddings.append({"chunk_data": chunk_data, "embedding": embedding})

            # Step 4: Index chunks into OpenSearch
            results = self.opensearch_client.bulk_index_chunks(chunks_with_embeddings)

            logger.info(f"Indexed paper {arxiv_id}: {results['success']} chunks successful, {results['failed']} failed")

            return {
                "chunks_created": len(chunks),
                "chunks_indexed": results["success"],
                "embeddings_generated": len(embeddings),
                "errors": results["failed"],
            }

        except Exception as e:
            logger.error(f"Error indexing paper {arxiv_id}: {e}")
            return {"chunks_created": 0, "chunks_indexed": 0, "embeddings_generated": 0, "errors": 1}

    async def index_papers_batch(self, papers: List[Dict], replace_existing: bool = False) -> Dict[str, int]:
        """Index multiple papers in batch.

        :param papers: List of paper data
        :param replace_existing: If True, delete existing chunks before indexing
        :returns: Aggregated statistics
        """
        total_stats = {
            "papers_processed": 0,
            "total_chunks_created": 0,
            "total_chunks_indexed": 0,
            "total_embeddings_generated": 0,
            "total_errors": 0,
        }

        for paper in papers:
            arxiv_id = paper.get("arxiv_id")

            # Optionally delete existing chunks
            if replace_existing and arxiv_id:
                self.opensearch_client.delete_paper_chunks(arxiv_id)

            # Index the paper
            stats = await self.index_paper(paper)

            # Update totals
            total_stats["papers_processed"] += 1
            total_stats["total_chunks_created"] += stats["chunks_created"]
            total_stats["total_chunks_indexed"] += stats["chunks_indexed"]
            total_stats["total_embeddings_generated"] += stats["embeddings_generated"]
            total_stats["total_errors"] += stats["errors"]

        logger.info(
            f"Batch indexing complete: {total_stats['papers_processed']} papers, "
            f"{total_stats['total_chunks_indexed']} chunks indexed"
        )

        return total_stats

    async def reindex_paper(self, arxiv_id: str, paper_data: Dict) -> Dict[str, int]:
        """Reindex a paper by deleting old chunks and creating new ones.

        :param arxiv_id: ArXiv ID of the paper
        :param paper_data: Updated paper data
        :returns: Indexing statistics
        """
        # Delete existing chunks
        deleted = self.opensearch_client.delete_paper_chunks(arxiv_id)
        if deleted:
            logger.info(f"Deleted existing chunks for paper {arxiv_id}")

        # Index with new data
        return await self.index_paper(paper_data)
