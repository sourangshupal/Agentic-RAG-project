from typing import Optional

from src.config import Settings, get_settings
from src.services.bedrock_guardrails.service import BedrockGuardrailsService
from src.services.embeddings.jina_client import JinaEmbeddingsClient
from src.services.langfuse.client import LangfuseTracer
from src.services.llm_client_protocol import LLMClientProtocol
from src.services.opensearch.client import OpenSearchClient

from .agentic_rag import AgenticRAGService
from .config import GraphConfig


def make_agentic_rag_service(
    opensearch_client: OpenSearchClient,
    llm_client: LLMClientProtocol,
    embeddings_client: JinaEmbeddingsClient,
    langfuse_tracer: Optional[LangfuseTracer] = None,
    guardrails_service: Optional[BedrockGuardrailsService] = None,
    top_k: int = 3,
    use_hybrid: bool = True,
    settings: Optional[Settings] = None,
) -> AgenticRAGService:
    """Create AgenticRAGService with dependency injection.

    Args:
        opensearch_client: Client for document search
        llm_client: LLM client (OpenAI or Bedrock)
        embeddings_client: Client for embeddings
        langfuse_tracer: Optional Langfuse tracer for observability
        guardrails_service: Optional Bedrock Guardrails service
        top_k: Number of documents to retrieve (default: 3)
        use_hybrid: Use hybrid search (default: True)
        settings: Application settings (reads model from .env)

    Returns:
        Configured AgenticRAGService instance
    """
    if settings is None:
        settings = get_settings()

    # Pick the model ID based on provider
    if settings.provider == "bedrock":
        model = settings.bedrock.model_id
    else:
        model = settings.openai_model

    graph_config = GraphConfig(
        top_k=top_k,
        use_hybrid=use_hybrid,
        model=model,
    )

    return AgenticRAGService(
        opensearch_client=opensearch_client,
        llm_client=llm_client,
        embeddings_client=embeddings_client,
        langfuse_tracer=langfuse_tracer,
        guardrails_service=guardrails_service,
        graph_config=graph_config,
    )
