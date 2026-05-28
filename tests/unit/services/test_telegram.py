import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.config import TelegramSettings
from src.services.telegram.bot import TelegramBot
from src.services.telegram.factory import make_telegram_service


class TestTelegramBot:
    """Test Telegram bot."""

    def test_bot_creation(self):
        """Test creating bot instance."""
        bot = TelegramBot(
            bot_token="test_token",
            opensearch_client=MagicMock(),
            embeddings_client=MagicMock(),
            llm_client=MagicMock(),
        )

        assert bot.bot_token == "test_token"
        assert bot.opensearch is not None
        assert bot.embeddings is not None
        assert bot.llm is not None


class TestTelegramBotAgenticMode:
    """Test bot uses agentic RAG when provided."""

    def test_bot_accepts_agentic_service(self):
        """TelegramBot stores agentic_rag_service."""
        agentic = MagicMock()
        bot = TelegramBot(
            bot_token="tok",
            opensearch_client=MagicMock(),
            embeddings_client=MagicMock(),
            llm_client=MagicMock(),
            agentic_rag_service=agentic,
        )
        assert bot.agentic_rag_service is agentic

    @pytest.mark.asyncio
    async def test_handle_question_calls_agentic(self):
        """_handle_question delegates to agentic_rag_service.ask()."""
        agentic = MagicMock()
        agentic.ask = AsyncMock(return_value={
            "answer": "Test answer",
            "sources": [{"arxiv_id": "2301.00001", "title": "Test Paper", "url": "https://arxiv.org/pdf/2301.00001.pdf"}],
            "reasoning_steps": ["Validated query", "Retrieved docs"],
            "retrieval_attempts": 1,
        })
        bot = TelegramBot(
            bot_token="tok",
            opensearch_client=MagicMock(),
            embeddings_client=MagicMock(),
            llm_client=MagicMock(),
            agentic_rag_service=agentic,
        )
        update = MagicMock()
        update.message.text = "What is BERT?"
        update.message.chat.send_action = AsyncMock()
        update.message.reply_text = AsyncMock()
        context = MagicMock()

        await bot._handle_question(update, context)

        agentic.ask.assert_called_once_with(query="What is BERT?", user_id=str(update.effective_user.id))
        update.message.reply_text.assert_called_once()


class TestTelegramSettings:
    """Test Telegram settings."""

    def test_default_settings(self):
        """Test default settings."""
        settings = TelegramSettings(bot_token="", enabled=False)
        assert settings.enabled is False
        assert settings.bot_token == ""

    def test_custom_settings(self):
        """Test custom settings."""
        settings = TelegramSettings(bot_token="test", enabled=True)
        assert settings.enabled is True
        assert settings.bot_token == "test"


class TestTelegramFactory:
    """Test factory."""

    @patch("src.services.telegram.factory.get_settings")
    def test_factory_disabled(self, mock_settings):
        """Test factory returns None when disabled."""
        mock_settings.return_value.telegram.enabled = False
        bot = make_telegram_service(
            opensearch_client=MagicMock(),
            embeddings_client=MagicMock(),
            llm_client=MagicMock(),
        )
        assert bot is None

    @patch("src.services.telegram.factory.get_settings")
    def test_factory_no_token(self, mock_settings):
        """Test factory returns None without token."""
        mock_settings.return_value.telegram.enabled = True
        mock_settings.return_value.telegram.bot_token = ""
        bot = make_telegram_service(
            opensearch_client=MagicMock(),
            embeddings_client=MagicMock(),
            llm_client=MagicMock(),
        )
        assert bot is None

    @patch("src.services.telegram.factory.get_settings")
    def test_factory_success(self, mock_settings):
        """Test factory creates bot."""
        mock_settings.return_value.telegram.enabled = True
        mock_settings.return_value.telegram.bot_token = "test_token"
        bot = make_telegram_service(
            opensearch_client=MagicMock(),
            embeddings_client=MagicMock(),
            llm_client=MagicMock(),
        )
        assert bot is not None
        assert bot.bot_token == "test_token"

    @patch("src.services.telegram.factory.get_settings")
    def test_factory_passes_agentic_service(self, mock_settings):
        """Factory passes agentic_rag_service to TelegramBot."""
        mock_settings.return_value.telegram.enabled = True
        mock_settings.return_value.telegram.bot_token = "test_token"
        agentic = MagicMock()
        bot = make_telegram_service(
            opensearch_client=MagicMock(),
            embeddings_client=MagicMock(),
            llm_client=MagicMock(),
            agentic_rag_service=agentic,
        )
        assert bot is not None
        assert bot.agentic_rag_service is agentic
