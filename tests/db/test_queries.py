import pytest

from src.db.database import Database
from src.db.queries import Queries


class TestArticleCRUD:
    async def test_create_article(self, queries: Queries):
        article = await queries.create_article(
            "https://example.com/article",
            "https://example.com/article",
        )
        assert article.id is not None
        assert article.url == "https://example.com/article"
        assert article.status == "pending"
        assert article.retry_count == 0
        assert article.chat_id is None

    async def test_create_article_with_chat_id(self, queries: Queries):
        article = await queries.create_article(
            "https://example.com/chat", "https://example.com/chat", chat_id=12345
        )
        assert article.chat_id == 12345

    async def test_get_article_by_id(self, queries: Queries):
        created = await queries.create_article("https://a.com/1", "https://a.com/1")
        found = await queries.get_article_by_id(created.id)
        assert found is not None
        assert found.url == "https://a.com/1"

    async def test_get_article_by_id_not_found(self, queries: Queries):
        found = await queries.get_article_by_id(9999)
        assert found is None

    async def test_get_article_by_normalized_url(self, queries: Queries):
        await queries.create_article("https://a.com/page?utm_source=x", "https://a.com/page")
        found = await queries.get_article_by_normalized_url("https://a.com/page")
        assert found is not None
        assert found.url == "https://a.com/page?utm_source=x"

    async def test_get_article_by_normalized_url_not_found(self, queries: Queries):
        found = await queries.get_article_by_normalized_url("https://nonexistent.com")
        assert found is None

    async def test_duplicate_url_raises(self, queries: Queries):
        import sqlite3

        await queries.create_article("https://a.com/dup", "https://a.com/dup")
        with pytest.raises(sqlite3.IntegrityError):
            await queries.create_article("https://a.com/dup", "https://a.com/dup")

    async def test_update_article_status(self, queries: Queries):
        article = await queries.create_article("https://a.com/u1", "https://a.com/u1")
        await queries.update_article_status(article.id, "processing")
        updated = await queries.get_article_by_id(article.id)
        assert updated is not None
        assert updated.status == "processing"

    async def test_update_article_with_optional_fields(self, queries: Queries):
        article = await queries.create_article("https://a.com/u2", "https://a.com/u2")
        await queries.update_article_status(
            article.id,
            "done",
            title="Test Title",
            summary="Test summary text",
            channel_message_id=42,
        )
        updated = await queries.get_article_by_id(article.id)
        assert updated is not None
        assert updated.status == "done"
        assert updated.title == "Test Title"
        assert updated.summary == "Test summary text"
        assert updated.channel_message_id == 42

    async def test_update_article_with_error(self, queries: Queries):
        article = await queries.create_article("https://a.com/u3", "https://a.com/u3")
        await queries.update_article_status(
            article.id, "failed", error_message="Connection timeout"
        )
        updated = await queries.get_article_by_id(article.id)
        assert updated is not None
        assert updated.status == "failed"
        assert updated.error_message == "Connection timeout"

    async def test_increment_retry_count(self, queries: Queries):
        article = await queries.create_article("https://a.com/rc", "https://a.com/rc")
        assert article.retry_count == 0

        new_count = await queries.increment_retry_count(article.id)
        assert new_count == 1

        new_count = await queries.increment_retry_count(article.id)
        assert new_count == 2

    async def test_increment_retry_count_nonexistent(self, queries: Queries):
        result = await queries.increment_retry_count(9999)
        assert result == 0


class TestArticleQueries:
    async def test_get_pending_articles(self, queries: Queries):
        a1 = await queries.create_article("https://a.com/p1", "https://a.com/p1")
        a2 = await queries.create_article("https://a.com/p2", "https://a.com/p2")
        await queries.update_article_status(a2.id, "done")
        a3 = await queries.create_article("https://a.com/p3", "https://a.com/p3")
        await queries.update_article_status(a3.id, "processing")

        pending = await queries.get_pending_articles()
        ids = [a.id for a in pending]
        assert a1.id in ids
        assert a3.id in ids
        assert a2.id not in ids

    async def test_get_failed_articles(self, queries: Queries):
        a1 = await queries.create_article("https://a.com/f1", "https://a.com/f1")
        await queries.update_article_status(a1.id, "failed", error_message="err")
        a2 = await queries.create_article("https://a.com/f2", "https://a.com/f2")
        await queries.update_article_status(a2.id, "done")

        failed = await queries.get_failed_articles()
        assert len(failed) == 1
        assert failed[0].id == a1.id

    async def test_reset_article_for_retry(self, queries: Queries):
        article = await queries.create_article("https://a.com/r1", "https://a.com/r1")
        await queries.update_article_status(article.id, "failed", error_message="err")
        await queries.reset_article_for_retry(article.id)
        updated = await queries.get_article_by_id(article.id)
        assert updated is not None
        assert updated.status == "pending"
        assert updated.error_message is None

    async def test_search_articles_by_summary(self, queries: Queries):
        a1 = await queries.create_article("https://a.com/s1", "https://a.com/s1")
        await queries.update_article_status(
            a1.id, "done", summary="Обзор архитектуры микросервисов"
        )
        a2 = await queries.create_article("https://a.com/s2", "https://a.com/s2")
        await queries.update_article_status(
            a2.id, "done", summary="Введение в машинное обучение"
        )

        results = await queries.search_articles_by_summary("микросервис")
        assert len(results) == 1
        assert results[0].id == a1.id

    async def test_search_articles_by_summary_escapes_special_chars(self, queries: Queries):
        a1 = await queries.create_article("https://a.com/esc1", "https://a.com/esc1")
        await queries.update_article_status(a1.id, "done", summary="100% working solution")
        a2 = await queries.create_article("https://a.com/esc2", "https://a.com/esc2")
        await queries.update_article_status(a2.id, "done", summary="something else")

        results = await queries.search_articles_by_summary("100%")
        assert len(results) == 1

    async def test_search_articles_by_summary_no_results(self, queries: Queries):
        results = await queries.search_articles_by_summary("nonexistent")
        assert results == []

    async def test_get_stats(self, queries: Queries):
        a1 = await queries.create_article("https://a.com/st1", "https://a.com/st1")
        await queries.update_article_status(a1.id, "done")
        a2 = await queries.create_article("https://a.com/st2", "https://a.com/st2")
        await queries.update_article_status(a2.id, "failed", error_message="err")
        await queries.create_article("https://a.com/st3", "https://a.com/st3")

        stats = await queries.get_stats()
        assert stats["total"] == 3
        assert stats["done"] == 1
        assert stats["failed"] == 1
        assert stats["tags"] == 0


class TestHashtagCRUD:
    async def test_get_or_create_hashtag_creates_new(self, queries: Queries):
        tag = await queries.get_or_create_hashtag("python")
        assert tag.id is not None
        assert tag.name == "python"

    async def test_get_or_create_hashtag_returns_existing(self, queries: Queries):
        tag1 = await queries.get_or_create_hashtag("python")
        tag2 = await queries.get_or_create_hashtag("python")
        assert tag1.id == tag2.id

    async def test_get_or_create_hashtag_normalizes(self, queries: Queries):
        tag1 = await queries.get_or_create_hashtag("#Python")
        tag2 = await queries.get_or_create_hashtag("python")
        assert tag1.id == tag2.id
        assert tag1.name == "python"

    async def test_get_or_create_hashtag_strips_whitespace(self, queries: Queries):
        tag = await queries.get_or_create_hashtag("  ai  ")
        assert tag.name == "ai"

    async def test_get_all_hashtags(self, queries: Queries):
        await queries.get_or_create_hashtag("alpha")
        await queries.get_or_create_hashtag("beta")
        await queries.get_or_create_hashtag("gamma")

        tags = await queries.get_all_hashtags()
        names = [t.name for t in tags]
        assert names == ["alpha", "beta", "gamma"]

    async def test_get_top_hashtags(self, queries: Queries):
        # Create tags and link with varying usage
        a1 = await queries.create_article("https://a.com/top1", "https://a.com/top1")
        a2 = await queries.create_article("https://a.com/top2", "https://a.com/top2")

        tag_popular = await queries.get_or_create_hashtag("popular")
        tag_rare = await queries.get_or_create_hashtag("rare")

        await queries.link_article_hashtags(a1.id, [tag_popular.id, tag_rare.id])
        await queries.link_article_hashtags(a2.id, [tag_popular.id])

        top = await queries.get_top_hashtags(limit=10)
        assert len(top) == 2
        assert top[0].name == "popular"  # used twice, should be first

    async def test_get_top_hashtags_with_limit(self, queries: Queries):
        for i in range(5):
            await queries.get_or_create_hashtag(f"tag{i}")

        top = await queries.get_top_hashtags(limit=3)
        assert len(top) == 3

    async def test_link_article_hashtags(self, queries: Queries):
        article = await queries.create_article("https://a.com/h1", "https://a.com/h1")
        tag1 = await queries.get_or_create_hashtag("python")
        tag2 = await queries.get_or_create_hashtag("asyncio")
        await queries.link_article_hashtags(article.id, [tag1.id, tag2.id])

        await queries.update_article_status(article.id, "done")
        found = await queries.search_articles_by_hashtag("python")
        assert len(found) == 1
        assert found[0].id == article.id

    async def test_link_article_hashtags_idempotent(self, queries: Queries):
        article = await queries.create_article("https://a.com/idem", "https://a.com/idem")
        tag = await queries.get_or_create_hashtag("rust")
        # Linking twice should not raise
        await queries.link_article_hashtags(article.id, [tag.id])
        await queries.link_article_hashtags(article.id, [tag.id])

    async def test_search_articles_by_hashtag(self, queries: Queries):
        a1 = await queries.create_article("https://a.com/ht1", "https://a.com/ht1")
        a2 = await queries.create_article("https://a.com/ht2", "https://a.com/ht2")
        await queries.update_article_status(a1.id, "done")
        await queries.update_article_status(a2.id, "done")

        tag = await queries.get_or_create_hashtag("rust")
        await queries.link_article_hashtags(a1.id, [tag.id])

        results = await queries.search_articles_by_hashtag("#rust")
        assert len(results) == 1
        assert results[0].id == a1.id

    async def test_search_articles_by_hashtag_no_results(self, queries: Queries):
        results = await queries.search_articles_by_hashtag("nonexistent")
        assert results == []

    async def test_stats_includes_tags(self, queries: Queries):
        await queries.get_or_create_hashtag("tag1")
        await queries.get_or_create_hashtag("tag2")

        stats = await queries.get_stats()
        assert stats["tags"] == 2


class TestDatabaseConnection:
    async def test_conn_raises_when_not_connected(self):
        db = Database(":memory:")
        with pytest.raises(RuntimeError, match="not connected"):
            _ = db.conn

    async def test_connect_and_close(self):
        db = Database(":memory:")
        await db.connect()
        assert db.conn is not None
        await db.close()
        with pytest.raises(RuntimeError):
            _ = db.conn
