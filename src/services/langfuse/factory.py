from functools import lru_cache

from src.config import get_settings
from src.services.langfuse.client import LangfuseTracer


@lru_cache(maxsize=1)
def make_langfuse_tracer() -> LangfuseTracer:
    """
    Create and return a singleton Langfuse tracer instance.

    Returns:
        LangfuseTracer: Configured Langfuse tracer
    """
    settings = get_settings()
    return LangfuseTracer(settings)
