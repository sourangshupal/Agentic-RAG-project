import logging
from typing import Optional

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

logger = logging.getLogger(__name__)


class TelegramBot:
    """Telegram bot for Q&A via agentic RAG pipeline."""

    def __init__(
        self,
        bot_token: str,
        opensearch_client,
        embeddings_client,
        llm_client,
        cache_client=None,
        agentic_rag_service=None,
    ):
        self.bot_token = bot_token
        self.opensearch = opensearch_client
        self.embeddings = embeddings_client
        self.llm = llm_client
        self.cache = cache_client
        self.agentic_rag_service = agentic_rag_service
        self.application: Optional[Application] = None

    async def start(self) -> None:
        """Start bot with polling."""
        logger.info("Starting Telegram bot...")
        self.application = Application.builder().token(self.bot_token).build()

        self.application.add_handler(CommandHandler("start", self._start_command))
        self.application.add_handler(CommandHandler("help", self._help_command))
        self.application.add_handler(CommandHandler("search", self._search_command))
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_question))

        await self.application.initialize()
        await self.application.start()
        await self.application.updater.start_polling()
        logger.info("Telegram bot started successfully")

    async def stop(self) -> None:
        """Stop bot."""
        if self.application:
            await self.application.updater.stop()
            await self.application.stop()
            await self.application.shutdown()
            logger.info("Telegram bot stopped")

    async def _start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /start."""
        await update.message.reply_text(
            "Welcome to arXiv Paper Curator!\n\n"
            "Ask me questions about CS papers and I'll provide answers with sources.\n\n"
            "Commands:\n"
            "/help - Show this help\n"
            "/search <keywords> - Search papers"
        )

    async def _help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /help."""
        await update.message.reply_text(
            "Send me any question about computer science research papers.\n\n"
            "Examples:\n"
            "- What are transformer architectures?\n"
            "- How does BERT work?\n"
            "- Explain attention mechanisms\n\n"
            "Use /search to find specific papers."
        )

    async def _search_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /search."""
        if not context.args:
            await update.message.reply_text("Usage: /search <keywords>\nExample: /search neural networks")
            return

        query = " ".join(context.args)
        await update.message.chat.send_action("typing")

        try:
            query_embedding = await self.embeddings.embed_query(query)
            results = self.opensearch.search_unified(
                query=query,
                query_embedding=query_embedding,
                size=10,
                use_hybrid=True,
            )

            hits = results.get("hits", [])
            if not hits:
                await update.message.reply_text("No papers found. Try different keywords.")
                return

            seen_ids: set = set()
            unique_papers = []
            for hit in hits:
                arxiv_id = hit.get("arxiv_id", "")
                if arxiv_id and arxiv_id not in seen_ids:
                    seen_ids.add(arxiv_id)
                    unique_papers.append(hit)
                if len(unique_papers) >= 5:
                    break

            response = f"Found {len(unique_papers)} papers:\n\n"
            for idx, hit in enumerate(unique_papers, 1):
                title = hit.get("title", "Untitled")
                arxiv_id = hit.get("arxiv_id", "")
                url = f"https://arxiv.org/abs/{arxiv_id}"
                response += f"{idx}. {title}\n{url}\n\n"

            await update.message.reply_text(response, disable_web_page_preview=True)

        except Exception as e:
            logger.error(f"Search failed: {e}", exc_info=True)
            await update.message.reply_text(f"Search failed: {str(e)}")

    async def _handle_question(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle user questions via agentic RAG pipeline."""
        query = update.message.text
        user_id = str(update.effective_user.id) if update.effective_user else "telegram_user"
        await update.message.chat.send_action("typing")

        try:
            if self.agentic_rag_service is None:
                await update.message.reply_text("RAG service unavailable.")
                return

            result = await self.agentic_rag_service.ask(query=query, user_id=user_id)
            await self._send_agentic_answer(update, result)

        except Exception as e:
            logger.error(f"Question handling failed: {e}", exc_info=True)
            await update.message.reply_text(f"Error: {str(e)}")

    async def _send_agentic_answer(self, update: Update, result: dict) -> None:
        """Format and send agentic RAG response."""
        answer = result.get("answer", "No answer generated.")
        sources = result.get("sources", [])

        message = f"*Answer:*\n{answer}\n"

        if sources:
            message += "\n*Sources:*\n"
            for idx, source in enumerate(sources[:5], 1):
                if isinstance(source, dict):
                    arxiv_id = source.get("arxiv_id", "")
                    title = source.get("title", "")
                    label = title if title else arxiv_id
                    message += f"{idx}. [{label}](https://arxiv.org/abs/{arxiv_id})\n"
                else:
                    message += f"{idx}. {source}\n"

        rewritten = result.get("rewritten_query")
        if rewritten and rewritten != result.get("query", ""):
            message += f"\n_Query refined to: {rewritten}_"

        try:
            await update.message.reply_text(message, parse_mode="Markdown", disable_web_page_preview=True)
        except Exception:
            await update.message.reply_text(answer, disable_web_page_preview=True)
