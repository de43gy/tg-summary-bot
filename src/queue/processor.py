import asyncio
import logging

from aiogram import Bot

from src.config import Config
from src.db.queries import Queries
from src.services.article_parser import fetch_and_parse
from src.services.formatter import format_channel_post
from src.services.summarizer import Summarizer

logger = logging.getLogger(__name__)


class QueueProcessor:
    def __init__(
        self,
        config: Config,
        queries: Queries,
        summarizer: Summarizer,
        bot: Bot,
    ) -> None:
        self._config = config
        self._queries = queries
        self._summarizer = summarizer
        self._bot = bot
        self._running = False
        self._lock = asyncio.Lock()

    async def process_article(self, article_id: int, reply_chat_id: int | None = None) -> bool:
        """Process a single article. Uses a lock to prevent double-processing."""
        async with self._lock:
            return await self._process_article_locked(article_id, reply_chat_id)

    async def _process_article_locked(
        self, article_id: int, reply_chat_id: int | None = None
    ) -> bool:
        """Internal: process a single article while holding the lock."""
        article = await self._queries.get_article_by_id(article_id)
        if not article:
            return False

        # Skip if already processed
        if article.status == "done":
            return False

        # Use stored chat_id as fallback for replies (e.g., after restart)
        chat_id = reply_chat_id or article.chat_id

        # Enforce retry limit
        if article.retry_count >= self._config.llm_max_retries:
            await self._queries.update_article_status(
                article.id,
                "failed",
                error_message=f"Превышен лимит попыток ({self._config.llm_max_retries})",
            )
            if chat_id:
                await self._bot.send_message(
                    chat_id,
                    f"Статья {article.url} превысила лимит попыток ({self._config.llm_max_retries}).",
                )
            return False

        await self._queries.increment_retry_count(article.id)
        await self._queries.update_article_status(article.id, "processing")

        # Step 1: fetch and parse
        parsed = await fetch_and_parse(article.url)
        if not parsed:
            error = f"Не удалось получить содержимое статьи: {article.url}"
            await self._queries.update_article_status(article.id, "failed", error_message=error)
            if chat_id:
                await self._bot.send_message(chat_id, error)
            return False

        # Step 2: summarize with LLM retries (within a single process_article call)
        existing_hashtags = await self._queries.get_top_hashtags(limit=50)
        result = None
        last_error = ""
        delay = self._config.llm_request_delay

        for attempt in range(1, self._config.llm_max_retries + 1):
            try:
                result = await self._summarizer.summarize(parsed.text, existing_hashtags)
                break
            except Exception as exc:
                last_error = str(exc)
                logger.warning(
                    "LLM attempt %d/%d failed: %s",
                    attempt,
                    self._config.llm_max_retries,
                    last_error,
                )
                if attempt < self._config.llm_max_retries:
                    await asyncio.sleep(delay)
                    delay = min(delay * 2, 60)

        if not result:
            await self._queries.update_article_status(
                article.id, "failed", error_message=f"LLM error: {last_error}"
            )
            if chat_id:
                await self._bot.send_message(
                    chat_id,
                    f"Ошибка при генерации конспекта для {article.url}. Попробуйте /retry {article.id}",
                )
            return False

        title = result["title"]
        summary = result["summary"]
        hashtag_names: list[str] = result["hashtags"]

        # Step 3: save hashtags
        hashtag_ids: list[int] = []
        for tag_name in hashtag_names:
            tag = await self._queries.get_or_create_hashtag(tag_name)
            hashtag_ids.append(tag.id)
        await self._queries.link_article_hashtags(article.id, hashtag_ids)

        # Step 4: format and post to channel
        post_parts = format_channel_post(title, summary, hashtag_names, article.url)
        try:
            last_msg = None
            for part in post_parts:
                last_msg = await self._bot.send_message(
                    self._config.telegram_channel_id, part
                )
                if len(post_parts) > 1:
                    await asyncio.sleep(1)  # rate limit between messages
        except Exception as exc:
            error = f"Не удалось отправить в канал: {exc}"
            logger.exception(error)
            await self._queries.update_article_status(
                article.id, "failed", title=title, summary=summary, error_message=error
            )
            if chat_id:
                await self._bot.send_message(chat_id, error)
            return False

        # Step 5: update DB
        await self._queries.update_article_status(
            article.id,
            "done",
            title=title,
            summary=summary,
            channel_message_id=last_msg.message_id if last_msg else None,
        )

        # Step 6: confirm to user
        if chat_id:
            await self._bot.send_message(
                chat_id,
                f"Конспект опубликован: {article.url}",
            )

        return True

    async def process_pending(self, reply_chat_id: int | None = None) -> None:
        """Process all pending articles sequentially."""
        articles = await self._queries.get_pending_articles()
        for article in articles:
            await self.process_article(article.id, reply_chat_id)
            await asyncio.sleep(self._config.llm_request_delay)

    async def start_background_loop(self) -> None:
        """Background loop that processes pending articles every 10 seconds."""
        self._running = True
        while self._running:
            try:
                pending = await self._queries.get_pending_articles()
                for article in pending:
                    if not self._running:
                        break
                    await self.process_article(article.id, article.chat_id)
                    await asyncio.sleep(self._config.llm_request_delay)
            except Exception:
                logger.exception("Error in background queue processor")
            await asyncio.sleep(10)

    def stop(self) -> None:
        self._running = False
