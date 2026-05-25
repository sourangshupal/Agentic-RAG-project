import logging
import os
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from src.config import get_settings
from src.db.factory import make_database
import logfire
from src.mcp_server.server import MCPContext, mcp, set_mcp_context
from src.services.logfire.factory import configure_logfire
from src.routers import agentic_ask, hybrid_search, ping
from src.routers.ask import ask_router, stream_router
from src.services.agents.factory import make_agentic_rag_service
from src.services.arxiv.factory import make_arxiv_client
from src.services.cache.factory import make_cache_client
from src.services.embeddings.factory import make_embeddings_service
from src.services.langfuse.factory import make_langfuse_tracer
from src.services.bedrock_guardrails.factory import make_bedrock_guardrails_service
from src.services.bedrock_llm.factory import make_bedrock_llm_client
from src.services.openai_llm.factory import make_openai_llm_client
from src.services.opensearch.factory import make_opensearch_client
from src.services.pdf_parser.factory import make_pdf_parser_service
from src.services.telegram.factory import make_telegram_service

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Create MCP HTTP app once at module level.
# path="/" places the route at "/" inside the sub-app so it matches when mounted at /mcp.
_mcp_http_app = mcp.http_app(path="/", stateless_http=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan for the API."""
    # MCP session manager must be started before any requests arrive.
    # All service init happens inside this context so the manager is alive
    # for the full duration the app is running.
    async with _mcp_http_app.lifespan(app):
        logger.info("Starting RAG API...")

        settings = get_settings()
        app.state.settings = settings

        # Configure Logfire first — wires stdlib logging bridge + auto-instrumentation.
        # Must run before any service factories so SQLAlchemy/Redis/httpx are instrumented
        # before their clients are created.
        configure_logfire(settings)
        if settings.logfire.enabled:
            logfire.instrument_fastapi(app, request_attributes_mapper=_skip_health)

        database = make_database()
        app.state.database = database
        logger.info("Database connected")

        # Initialize search service
        opensearch_client = make_opensearch_client()
        app.state.opensearch_client = opensearch_client

        if opensearch_client.health_check():
            logger.info("OpenSearch connected successfully")

            setup_results = opensearch_client.setup_indices(force=False)
            if setup_results.get("hybrid_index"):
                logger.info("Hybrid index created")
            else:
                logger.info("Hybrid index already exists")

            try:
                stats = opensearch_client.client.count(index=opensearch_client.index_name)
                logger.info(f"OpenSearch ready: {stats['count']} documents indexed")
            except Exception:
                logger.info("OpenSearch index ready (stats unavailable)")
        else:
            logger.warning("OpenSearch connection failed - search features will be limited")

        # Initialize other services
        app.state.arxiv_client = make_arxiv_client()
        app.state.pdf_parser = make_pdf_parser_service()
        app.state.embeddings_service = make_embeddings_service()
        if settings.provider == "bedrock":
            app.state.llm_client = make_bedrock_llm_client(settings)
            logger.info(f"LLM provider: AWS Bedrock (model={settings.bedrock.model_id})")
        else:
            app.state.llm_client = make_openai_llm_client()
            logger.info(f"LLM provider: OpenAI (model={settings.openai_model})")

        app.state.guardrails_service = make_bedrock_guardrails_service(settings)
        guardrail_status = f"guardrail_id={settings.bedrock.guardrail_id}" if settings.bedrock.guardrail_id else "disabled (no guardrail_id)"
        logger.info(f"Bedrock Guardrails: {guardrail_status}")

        app.state.langfuse_tracer = make_langfuse_tracer()
        app.state.cache_client = make_cache_client(settings)
        logger.info("Services initialized: arXiv API client, PDF parser, OpenSearch, Embeddings, LLM, Guardrails, Langfuse, Cache")

        # Wire MCP context so tools can reach all services
        if settings.mcp.enabled:
            agentic_rag_for_mcp = make_agentic_rag_service(
                opensearch_client=app.state.opensearch_client,
                llm_client=app.state.llm_client,
                embeddings_client=app.state.embeddings_service,
                langfuse_tracer=app.state.langfuse_tracer,
                guardrails_service=app.state.guardrails_service,
            )
            set_mcp_context(
                MCPContext(
                    opensearch_client=app.state.opensearch_client,
                    embeddings_client=app.state.embeddings_service,
                    llm_client=app.state.llm_client,
                    langfuse_tracer=app.state.langfuse_tracer,
                    agentic_rag_service=agentic_rag_for_mcp,
                    database=app.state.database,
                )
            )
            logger.info(f"MCP server context ready (mounted at {settings.mcp.path})")

        # Initialize Telegram bot (Phase 7)
        telegram_service = make_telegram_service(
            opensearch_client=app.state.opensearch_client,
            embeddings_client=app.state.embeddings_service,
            llm_client=app.state.llm_client,
            cache_client=app.state.cache_client,
            langfuse_tracer=app.state.langfuse_tracer,
        )

        if telegram_service:
            app.state.telegram_service = telegram_service
            try:
                await telegram_service.start()
                logger.info("Telegram bot started successfully")
            except Exception as e:
                logger.error(f"Failed to start Telegram bot: {e}")
        else:
            logger.info("Telegram bot not configured - skipping initialization")

        logger.info("API ready")
        yield

        # Cleanup
        if hasattr(app.state, "telegram_service") and app.state.telegram_service:
            await app.state.telegram_service.stop()
            logger.info("Telegram bot stopped")

        database.teardown()
        logger.info("API shutdown complete")


app = FastAPI(
    title="arXiv Paper Curator API",
    description="Personal arXiv CS.AI paper curator with RAG capabilities",
    version=os.getenv("APP_VERSION", "0.1.0"),
    lifespan=lifespan,
)

def _skip_health(request, attributes):
    return {} if request.url.path == "/api/v1/health" else attributes

# Include routers
app.include_router(ping.router, prefix="/api/v1")
app.include_router(hybrid_search.router, prefix="/api/v1")
app.include_router(ask_router, prefix="/api/v1")
app.include_router(stream_router, prefix="/api/v1")
app.include_router(agentic_ask.router)

# Mount MCP sub-app (lifespan is composed inside the main lifespan above)
_mcp_settings = get_settings().mcp
if _mcp_settings.enabled:
    app.mount(_mcp_settings.path, _mcp_http_app)


if __name__ == "__main__":
    uvicorn.run(app, port=8000, host="0.0.0.0")
