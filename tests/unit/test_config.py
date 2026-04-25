import pytest
from src.config import Settings


def test_settings_initialization():
    """Test settings can be initialized."""
    settings = Settings()

    assert settings.app_version == "0.1.0"
    assert settings.debug is True
    assert settings.environment == "development"
    assert settings.service_name == "rag-api"


def test_settings_postgres_defaults():
    """Test PostgreSQL default configuration."""
    settings = Settings()

    assert "postgresql://" in settings.postgres_database_url
    assert settings.postgres_echo_sql is False
    assert settings.postgres_pool_size == 5
    assert settings.postgres_max_overflow == 0


def test_settings_opensearch_defaults():
    """Test OpenSearch default configuration."""
    settings = Settings()

    assert settings.opensearch.host == "http://localhost:9200"
    assert settings.opensearch.index_name == "arxiv-papers"


def test_settings_openai_defaults():
    """Test OpenAI default configuration."""
    settings = Settings()

    assert settings.openai_model == "gpt-4o-mini"
    assert settings.openai_timeout == 300
