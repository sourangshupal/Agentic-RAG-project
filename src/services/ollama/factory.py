from functools import lru_cache

from src.config import get_settings
from src.services.ollama.client import OllamaClient


@lru_cache(maxsize=1)
def make_ollama_client() -> OllamaClient:
    """
    Create and return a singleton Ollama client instance.

    Returns:
        OllamaClient: Configured Ollama client
    """
    settings = get_settings()
    return OllamaClient(settings)
