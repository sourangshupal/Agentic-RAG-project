from src.config import Settings, get_settings
from src.services.bedrock_llm.client import BedrockLLMClient


def make_bedrock_llm_client(settings: Settings | None = None) -> BedrockLLMClient:
    """Create and return a Bedrock LLM client."""
    if settings is None:
        settings = get_settings()
    return BedrockLLMClient(settings)
