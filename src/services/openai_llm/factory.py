from functools import lru_cache

from src.config import get_settings
from src.services.openai_llm.client import OpenAILLMClient


@lru_cache(maxsize=1)
def make_openai_llm_client() -> OpenAILLMClient:
    """Create and return a singleton OpenAI LLM client."""
    settings = get_settings()
    return OpenAILLMClient(settings)
