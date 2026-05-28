import logging

import logfire

from src.config import Settings

logger = logging.getLogger(__name__)


def configure_logfire(settings: Settings) -> None:
    """Configure Logfire and wire auto-instrumentation. Called once at startup.

    When LOGFIRE__TOKEN is blank, Logfire prints structured output to console
    but sends nothing to the cloud — safe for local dev with no account needed.
    Langfuse owns all LLM semantic traces; Logfire owns infrastructure observability.
    """
    if not settings.logfire.enabled:
        logger.info("Logfire disabled (LOGFIRE__ENABLED=false)")
        return

    logfire.configure(
        token=settings.logfire.token or None,
        service_name=settings.logfire.service_name,
        environment=settings.logfire.environment,
        send_to_logfire=settings.logfire.send_to_logfire,
    )

    # Infrastructure auto-instrumentation.
    # NOTE: intentionally NOT calling logfire.instrument_openai() —
    # Langfuse already owns rich LLM semantic traces (prompts, tokens, cost).
    # logfire.instrument_httpx() still captures raw HTTP to api.openai.com
    # at the transport level (URL, status, latency) which complements Langfuse.
    logfire.instrument_sqlalchemy()   # Neon PostgreSQL queries via SQLAlchemy
    logfire.instrument_redis()        # Upstash Redis cache GET/SET ops
    logfire.instrument_httpx()        # Jina embeddings, arXiv API, all outbound HTTP
    logfire.instrument_pydantic()     # Pydantic model validation events

    logger.info(
        f"Logfire configured — service={settings.logfire.service_name} "
        f"env={settings.logfire.environment} "
        f"send={settings.logfire.send_to_logfire}"
    )
