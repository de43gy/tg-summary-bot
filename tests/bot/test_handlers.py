from unittest.mock import AsyncMock, MagicMock

from src.bot.handlers import cmd_retry, cmd_search, cmd_start, cmd_stats, handle_message
from src.db.queries import Queries


def _make_message(text: str = "", chat_id: int = 111, chat_type: str = "private") -> MagicMock:
    msg = AsyncMock()
    msg.text = text
    msg.caption = None
    msg.chat = MagicMock()
    msg.chat.id = chat_id
    msg.chat.type = chat_type
    msg.answer = AsyncMock()
    return msg


class TestCmdStart:
    async def test_start_sends_welcome(self):
        msg = _make_message("/start")
        await cmd_start(msg)
        msg.answer.assert_called_once()
        text = msg.answer.call_args[0][0]
        assert "Привет" in text
        assert "/search" in text
        assert "/stats" in text


class TestCmdStats:
    async def test_stats_displays_counts(self, queries: Queries):
        a = await queries.create_article("https://a.com/1", "https://a.com/1")
        await queries.update_article_status(a.id, "done")
        await queries.get_or_create_hashtag("tag1")

        msg = _make_message("/stats")
        await cmd_stats(msg, queries)
        msg.answer.assert_called_once()
        text = msg.answer.call_args[0][0]
        assert "1" in text
        assert "Хештегов" in text


class TestCmdSearch:
    async def test_search_no_args(self, queries: Queries):
        msg = _make_message("/search")
        await cmd_search(msg, queries)
        msg.answer.assert_called_once()
        assert "Использование" in msg.answer.call_args[0][0]

    async def test_search_empty_args(self, queries: Queries):
        msg = _make_message("/search   ")
        await cmd_search(msg, queries)
        msg.answer.assert_called_once()
        assert "Использование" in msg.answer.call_args[0][0]

    async def test_search_by_hashtag(self, queries: Queries):
        a = await queries.create_article("https://a.com/h1", "https://a.com/h1")
        await queries.update_article_status(a.id, "done", title="Python Tips")
        tag = await queries.get_or_create_hashtag("python")
        await queries.link_article_hashtags(a.id, [tag.id])

        msg = _make_message("/search #python")
        await cmd_search(msg, queries)
        msg.answer.assert_called_once()
        text = msg.answer.call_args[0][0]
        assert "Python Tips" in text

    async def test_search_by_keyword(self, queries: Queries):
        a = await queries.create_article("https://a.com/kw1", "https://a.com/kw1")
        await queries.update_article_status(
            a.id, "done", title="ML Article", summary="Обзор нейросетей и глубокого обучения"
        )

        msg = _make_message("/search нейросет")
        await cmd_search(msg, queries)
        msg.answer.assert_called_once()
        text = msg.answer.call_args[0][0]
        assert "ML Article" in text

    async def test_search_no_results(self, queries: Queries):
        msg = _make_message("/search nonexistent_xyz")
        await cmd_search(msg, queries)
        msg.answer.assert_called_once()
        assert "Ничего не найдено" in msg.answer.call_args[0][0]


class TestCmdRetry:
    async def test_retry_specific_article(self, queries: Queries):
        a = await queries.create_article("https://a.com/r1", "https://a.com/r1")
        await queries.update_article_status(a.id, "failed", error_message="err")

        msg = _make_message(f"/retry {a.id}")
        await cmd_retry(msg, queries)

        msg.answer.assert_called_once()
        assert "повторную обработку" in msg.answer.call_args[0][0]

        updated = await queries.get_article_by_id(a.id)
        assert updated.status == "pending"

    async def test_retry_article_not_found(self, queries: Queries):
        msg = _make_message("/retry 9999")
        await cmd_retry(msg, queries)
        msg.answer.assert_called_once()
        assert "не найдена" in msg.answer.call_args[0][0]

    async def test_retry_article_not_failed(self, queries: Queries):
        a = await queries.create_article("https://a.com/r2", "https://a.com/r2")
        await queries.update_article_status(a.id, "done")

        msg = _make_message(f"/retry {a.id}")
        await cmd_retry(msg, queries)
        msg.answer.assert_called_once()
        assert "failed" in msg.answer.call_args[0][0]

    async def test_retry_all_failed(self, queries: Queries):
        a1 = await queries.create_article("https://a.com/ra1", "https://a.com/ra1")
        await queries.update_article_status(a1.id, "failed", error_message="e1")
        a2 = await queries.create_article("https://a.com/ra2", "https://a.com/ra2")
        await queries.update_article_status(a2.id, "failed", error_message="e2")

        msg = _make_message("/retry")
        await cmd_retry(msg, queries)

        msg.answer.assert_called_once()
        assert "2 статей" in msg.answer.call_args[0][0]

    async def test_retry_no_failed(self, queries: Queries):
        msg = _make_message("/retry")
        await cmd_retry(msg, queries)
        msg.answer.assert_called_once()
        assert "Нет статей с ошибками" in msg.answer.call_args[0][0]


class TestHandleMessage:
    async def test_message_with_url(self, queries: Queries):
        msg = _make_message("Check this: https://example.com/article")
        await handle_message(msg, queries)

        msg.answer.assert_called_once()
        assert "добавлена в очередь" in msg.answer.call_args[0][0]

        article = await queries.get_article_by_normalized_url("https://example.com/article")
        assert article is not None
        assert article.chat_id == 111

    async def test_message_without_url(self, queries: Queries):
        msg = _make_message("just some text without links")
        await handle_message(msg, queries)
        msg.answer.assert_not_called()

    async def test_duplicate_url_done(self, queries: Queries):
        a = await queries.create_article("https://example.com/dup", "https://example.com/dup")
        await queries.update_article_status(a.id, "done")

        msg = _make_message("https://example.com/dup")
        await handle_message(msg, queries)
        msg.answer.assert_called_once()
        assert "уже обработана" in msg.answer.call_args[0][0]

    async def test_duplicate_url_pending(self, queries: Queries):
        await queries.create_article("https://example.com/pend", "https://example.com/pend")

        msg = _make_message("https://example.com/pend")
        await handle_message(msg, queries)
        msg.answer.assert_called_once()
        assert "уже в очереди" in msg.answer.call_args[0][0]

    async def test_duplicate_url_failed(self, queries: Queries):
        a = await queries.create_article("https://example.com/fail", "https://example.com/fail")
        await queries.update_article_status(a.id, "failed", error_message="err")

        msg = _make_message("https://example.com/fail")
        await handle_message(msg, queries)
        msg.answer.assert_called_once()
        assert "/retry" in msg.answer.call_args[0][0]

    async def test_message_with_multiple_urls(self, queries: Queries):
        msg = _make_message("Links: https://a.com/1 and https://b.com/2")
        await handle_message(msg, queries)
        assert msg.answer.call_count == 2

    async def test_caption_url(self, queries: Queries):
        msg = _make_message("")
        msg.text = None
        msg.caption = "https://example.com/caption-link"
        await handle_message(msg, queries)

        msg.answer.assert_called_once()
        assert "добавлена в очередь" in msg.answer.call_args[0][0]
