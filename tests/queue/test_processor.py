from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.config import Config
from src.db.queries import Queries
from src.queue.processor import QueueProcessor
from src.services.article_parser import ParsedArticle
from src.services.summarizer import Summarizer


@pytest.fixture
def mock_bot():
    bot = AsyncMock()
    bot.send_message = AsyncMock()
    msg = MagicMock()
    msg.message_id = 100
    bot.send_message.return_value = msg
    return bot


@pytest.fixture
def mock_summarizer():
    summarizer = AsyncMock(spec=Summarizer)
    summarizer.summarize = AsyncMock(return_value={
        "title": "Тестовый заголовок",
        "summary": "Тестовый конспект статьи",
        "commentary": "Полезность: высокая.",
        "hashtags": ["python", "testing"],
    })
    return summarizer


@pytest.fixture
async def processor(config: Config, queries: Queries, mock_bot, mock_summarizer):
    return QueueProcessor(config, queries, mock_summarizer, mock_bot)


class TestProcessArticle:
    async def test_successful_processing(self, processor, queries, mock_bot, config):
        article = await queries.create_article("https://example.com/good", "https://example.com/good", chat_id=12345)

        parsed = ParsedArticle(url="https://example.com/good", title="Good Article", text="Content")

        with patch("src.queue.processor.fetch_and_parse", return_value=parsed):
            result = await processor.process_article(article.id, reply_chat_id=12345)

        assert result is True

        updated = await queries.get_article_by_id(article.id)
        assert updated.status == "done"
        assert updated.title == "Тестовый заголовок"
        assert updated.channel_message_id == 100

        # Verify bot posted to channel (conspect + commentary reply)
        channel_calls = [
            c for c in mock_bot.send_message.call_args_list
            if c[0][0] == config.telegram_channel_id
        ]
        assert len(channel_calls) == 2  # post + commentary reply

    async def test_article_not_found(self, processor):
        result = await processor.process_article(9999)
        assert result is False

    async def test_fetch_fails(self, processor, queries, mock_bot):
        article = await queries.create_article("https://example.com/bad", "https://example.com/bad", chat_id=12345)

        with patch("src.queue.processor.fetch_and_parse", return_value=None):
            result = await processor.process_article(article.id, reply_chat_id=12345)

        assert result is False

        updated = await queries.get_article_by_id(article.id)
        assert updated.status == "failed"
        assert "Не удалось получить содержимое" in updated.error_message

        # Verify error message sent to user
        user_calls = [
            c for c in mock_bot.send_message.call_args_list
            if c[0][0] == 12345
        ]
        assert len(user_calls) == 1

    async def test_llm_fails_all_retries(self, processor, queries, mock_bot, mock_summarizer):
        article = await queries.create_article("https://example.com/llm-fail", "https://example.com/llm-fail", chat_id=12345)
        parsed = ParsedArticle(url="https://example.com/llm-fail", title="T", text="C")

        mock_summarizer.summarize = AsyncMock(side_effect=Exception("LLM timeout"))

        with patch("src.queue.processor.fetch_and_parse", return_value=parsed):
            result = await processor.process_article(article.id, reply_chat_id=12345)

        assert result is False

        updated = await queries.get_article_by_id(article.id)
        assert updated.status == "failed"
        assert "LLM error" in updated.error_message

    async def test_llm_succeeds_on_retry(self, processor, queries, mock_bot, mock_summarizer):
        article = await queries.create_article("https://example.com/retry-ok", "https://example.com/retry-ok")
        parsed = ParsedArticle(url="https://example.com/retry-ok", title="T", text="C")

        call_count = 0

        async def flaky_summarize(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise Exception("Temporary failure")
            return {
                "title": "Восстановленный заголовок",
                "summary": "Конспект",
                "commentary": "Полезность: средняя.",
                "hashtags": ["test"],
            }

        mock_summarizer.summarize = flaky_summarize

        with patch("src.queue.processor.fetch_and_parse", return_value=parsed):
            result = await processor.process_article(article.id)

        assert result is True
        updated = await queries.get_article_by_id(article.id)
        assert updated.status == "done"

    async def test_no_reply_uses_stored_chat_id(self, processor, queries, mock_bot):
        article = await queries.create_article(
            "https://example.com/stored", "https://example.com/stored", chat_id=77777
        )

        with patch("src.queue.processor.fetch_and_parse", return_value=None):
            result = await processor.process_article(article.id, reply_chat_id=None)

        assert result is False
        # Error should have been sent to stored chat_id
        user_calls = [
            c for c in mock_bot.send_message.call_args_list
            if c[0][0] == 77777
        ]
        assert len(user_calls) == 1

    async def test_hashtags_saved_to_db(self, processor, queries, mock_bot):
        article = await queries.create_article("https://example.com/tags", "https://example.com/tags")
        parsed = ParsedArticle(url="https://example.com/tags", title="T", text="C")

        with patch("src.queue.processor.fetch_and_parse", return_value=parsed):
            await processor.process_article(article.id)

        tags = await queries.get_all_hashtags()
        tag_names = [t.name for t in tags]
        assert "python" in tag_names
        assert "testing" in tag_names

    async def test_skips_already_done_articles(self, processor, queries):
        article = await queries.create_article("https://example.com/done", "https://example.com/done")
        await queries.update_article_status(article.id, "done")

        result = await processor.process_article(article.id)
        assert result is False

    async def test_retry_limit_exceeded(self, processor, queries, config, mock_bot):
        article = await queries.create_article(
            "https://example.com/exhaust", "https://example.com/exhaust", chat_id=999
        )
        # Exhaust retries
        for _ in range(config.llm_max_retries):
            await queries.increment_retry_count(article.id)

        result = await processor.process_article(article.id, reply_chat_id=999)
        assert result is False

        updated = await queries.get_article_by_id(article.id)
        assert updated.status == "failed"
        assert "лимит попыток" in updated.error_message


class TestProcessPending:
    async def test_processes_all_pending(self, processor, queries):
        a1 = await queries.create_article("https://example.com/q1", "https://example.com/q1")
        a2 = await queries.create_article("https://example.com/q2", "https://example.com/q2")

        parsed = ParsedArticle(url="test", title="T", text="C")

        with patch("src.queue.processor.fetch_and_parse", return_value=parsed):
            await processor.process_pending()

        for aid in [a1.id, a2.id]:
            a = await queries.get_article_by_id(aid)
            assert a.status == "done"


class TestBackgroundLoop:
    async def test_stop_flag(self, processor):
        processor.stop()
        assert processor._running is False
