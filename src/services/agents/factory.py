from typing import Optional

from src.config import Settings, get_settings
from src.services.embeddings.jina_client import JinaEmbeddingsClient
from src.services.langfuse.client import LangfuseTracer
from src.services.openai_llm.client import OpenAILLMClient
from src.services.opensearch.client import OpenSearchClient

from .agentic_rag import AgenticRAGService
from .config import GraphConfig


def make_agentic_rag_service(
    opensearch_client: OpenSearchClient,
    llm_client: OpenAILLMClient,
    embeddings_client: JinaEmbeddingsClient,
    langfuse_tracer: Optional[LangfuseTracer] = None,
    top_k: int = 3,
    use_hybrid: bool = True,
    settings: Optional[Settings] = None,
) -> AgenticRAGService:
    """
    Create AgenticRAGService with dependency injection.

    Args:
        opensearch_client: Client for document search
        llm_client: OpenAI LLM client for generation
        embeddings_client: Client for embeddings
        langfuse_tracer: Optional Langfuse tracer for observability
        top_k: Number of documents to retrieve (default: 3)
        use_hybrid: Use hybrid search (default: True)
        settings: Application settings (reads OPENAI_MODEL from .env)

    Returns:
        Configured AgenticRAGService instance
    """
    if settings is None:
        settings = get_settings()

    graph_config = GraphConfig(
        top_k=top_k,
        use_hybrid=use_hybrid,
        model=settings.openai_model,
    )

    return AgenticRAGService(
        opensearch_client=opensearch_client,
        llm_client=llm_client,
        embeddings_client=embeddings_client,
        langfuse_tracer=langfuse_tracer,
        graph_config=graph_config,
    )
