from src.config import Settings, get_settings
from src.services.bedrock_guardrails.service import BedrockGuardrailsService


def make_bedrock_guardrails_service(settings: Settings | None = None) -> BedrockGuardrailsService:
    """Create and return a Bedrock Guardrails service instance."""
    if settings is None:
        settings = get_settings()
    return BedrockGuardrailsService(settings)
