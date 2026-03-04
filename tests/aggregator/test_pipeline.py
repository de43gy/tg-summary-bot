from __future__ import annotations

import hashlib
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.aggregator.pipeline import ContentPipeline, PipelineContext
from src.aggregator.sources.base import ContentItem, ContentSource, SOURCE_REGISTRY
from src.config import Config
from src.db.database import Database
from src.db.queries import Queries


# ── Helpers ────────────────────────────────────────────────────


class FakeSource(ContentSource):
    name = "fake"

    def __init__(self, items: list[ContentItem] | None = None) -> None:
        self._items = items or []

    async def fetch(self) -> list[ContentItem]:
        return self._items

    async def health_check(self) -> bool:
        return True


class FailingSource(ContentSource):
    name = "failing"

    async def fetch(self) -> list[ContentItem]:
        raise RuntimeError("Source exploded")

    async def health_check(self) -> bool:
        return False


def _make_item(source: str = "fake", url: str = "https://example.com/1", title: str = "Title") -> ContentItem:
    return ContentItem(source_name=source, title=title, url=url, text="Some content text")


# ── Fixtures ───────────────────────────────────────────────────


@pytest.fixture
def mock_bot():
    bot = AsyncMock()
    bot.send_message = AsyncMock()
    return bot


@pytest.fixture
def mock_llm():
    llm = AsyncMock()
    llm.complete = AsyncMock(
        return_value=json.dumps(
            {
                "title": "Тестовый дайджест",
                "summary": "Краткий обзор новостей за день",
                "hashtags": ["ml", "новости"],
            }
        )
    )
    return llm


@pytest.fixture
def aggregator_config() -> Config:
    return Config(
        telegram_bot_token="test-token",
        telegram_channel_id=-1001234567890,
        telegram_admin_id=123456789,
        openrouter_api_key="test-key",
        custom_llm_api_url=None,
        custom_llm_api_key=None,
        custom_llm_model=None,
        llm_request_delay=0.01,
        llm_max_retries=3,
        db_path=":memory:",
        aggregator_enabled=True,
        aggregator_enabled_sources=["fake"],
        aggregator_schedule="60",
        aggregator_tone="default",
    )


@pytest.fixture
async def agg_db() -> Database:
    database = Database(":memory:")
    await database.connect()
    yield database
    await database.close()


@pytest.fixture
async def agg_queries(agg_db: Database) -> Queries:
    return Queries(agg_db)


@pytest.fixture
def pipeline(aggregator_config, agg_queries, mock_llm, mock_bot) -> ContentPipeline:
    p = ContentPipeline(aggregator_config, agg_queries, mock_llm, mock_bot)
    return p


# ── Stage tests ────────────────────────────────────────────────


class TestStageCollect:
    async def test_collect_populates_items(self, pipeline):
        items = [_make_item(), _make_item(url="https://example.com/2")]
        pipeline._sources = {"fake": FakeSource(items)}

        ctx = PipelineContext()
        await pipeline._stage_collect(ctx)
        assert len(ctx.items) == 2

    async def test_collect_parallel_multiple_sources(self, pipeline):
        items_a = [_make_item(source="src_a", url="https://a.com/1")]
        items_b = [_make_item(source="src_b", url="https://b.com/1")]
        pipeline._sources = {
            "src_a": FakeSource(items_a),
            "src_b": FakeSource(items_b),
        }

        ctx = PipelineContext()
        await pipeline._stage_collect(ctx)
        assert len(ctx.items) == 2
        sources_collected = {i.source_name for i in ctx.items}
        assert sources_collected == {"src_a", "src_b"}

    async def test_collect_source_error_does_not_break_others(self, pipeline):
        items_ok = [_make_item(source="ok_src", url="https://ok.com/1")]
        pipeline._sources = {
            "failing": FailingSource(),
            "ok_src": FakeSource(items_ok),
        }

        ctx = PipelineContext()
        await pipeline._stage_collect(ctx)
        assert len(ctx.items) == 1
        assert ctx.items[0].source_name == "ok_src"


class TestStageDeduplicate:
    async def test_first_run_marks_all_new(self, pipeline, agg_queries):
        pipeline._sources = {"fake": FakeSource()}
        items = [_make_item(url="https://example.com/1"), _make_item(url="https://example.com/2")]

        ctx = PipelineContext(items=items)
        await pipeline._stage_deduplicate(ctx)
        assert len(ctx.new_items) == 2

    async def test_second_run_filters_duplicates(self, pipeline, agg_queries):
        pipeline._sources = {"fake": FakeSource()}
        items = [_make_item(url="https://example.com/1")]

        # First run
        ctx1 = PipelineContext(items=list(items))
        await pipeline._stage_deduplicate(ctx1)
        assert len(ctx1.new_items) == 1

        # Second run with same items
        ctx2 = PipelineContext(items=list(items))
        await pipeline._stage_deduplicate(ctx2)
        assert len(ctx2.new_items) == 0


class TestStageGenerate:
    async def test_generate_populates_ctx(self, pipeline, mock_llm):
        pipeline._sources = {"fake": FakeSource()}
        ctx = PipelineContext(
            new_items=[_make_item(), _make_item(url="https://example.com/2")]
        )

        await pipeline._stage_generate(ctx)
        assert ctx.generated_title == "Тестовый дайджест"
        assert ctx.generated_summary == "Краткий обзор новостей за день"
        assert ctx.generated_hashtags == ["ml", "новости"]
        assert len(ctx.source_urls) == 2
        mock_llm.complete.assert_called_once()

    async def test_generate_llm_failure_leaves_empty(self, pipeline, mock_llm):
        pipeline._sources = {"fake": FakeSource()}
        mock_llm.complete = AsyncMock(side_effect=RuntimeError("LLM down"))

        ctx = PipelineContext(new_items=[_make_item()])
        await pipeline._stage_generate(ctx)
        assert ctx.generated_summary == ""
        assert ctx.generated_title == ""


class TestStageFormat:
    def test_format_builds_post_text(self, pipeline):
        ctx = PipelineContext(
            generated_title="Заголовок",
            generated_summary="Текст дайджеста",
            generated_hashtags=["ml", "ai"],
            source_urls=["https://example.com/1", "https://example.com/2"],
        )
        pipeline._stage_format(ctx)
        assert "Заголовок" in ctx.post_text
        assert "Текст дайджеста" in ctx.post_text
        assert "#ml" in ctx.post_text
        assert "#ai" in ctx.post_text
        assert "Источники:" in ctx.post_text
        assert "https://example.com/1" in ctx.post_text


class TestStagePublish:
    async def test_publish_sends_to_channel(self, pipeline, mock_bot, aggregator_config):
        pipeline._sources = {"fake": FakeSource()}
        ctx = PipelineContext(
            post_text="Test post text",
            generated_hashtags=["tag1"],
        )

        await pipeline._stage_publish(ctx)
        mock_bot.send_message.assert_called_once_with(
            aggregator_config.telegram_channel_id,
            "Test post text",
            disable_web_page_preview=True,
        )


# ── Full pipeline run tests ───────────────────────────────────


class TestPipelineRun:
    async def test_run_full_success(self, pipeline, mock_bot, mock_llm, aggregator_config):
        items = [_make_item()]
        pipeline._sources = {"fake": FakeSource(items)}

        result = await pipeline.run()
        assert result is True
        mock_bot.send_message.assert_called()

        # Verify channel post was sent
        channel_calls = [
            c for c in mock_bot.send_message.call_args_list
            if c[0][0] == aggregator_config.telegram_channel_id
        ]
        assert len(channel_calls) == 1

    async def test_run_no_items(self, pipeline):
        pipeline._sources = {"fake": FakeSource([])}

        result = await pipeline.run()
        assert result is False

    async def test_run_all_duplicates(self, pipeline, agg_queries):
        items = [_make_item()]
        pipeline._sources = {"fake": FakeSource(items)}

        # First run succeeds
        result1 = await pipeline.run()
        assert result1 is True

        # Second run — all duplicates
        result2 = await pipeline.run()
        assert result2 is False

    async def test_run_notifies_admin_on_error(self, pipeline, mock_bot, aggregator_config):
        pipeline._sources = {"fake": FakeSource([_make_item()])}

        # Force an error in _stage_deduplicate
        pipeline._stage_deduplicate = AsyncMock(side_effect=RuntimeError("DB broke"))

        with pytest.raises(RuntimeError, match="DB broke"):
            await pipeline.run()

        # Admin should have been notified
        admin_calls = [
            c for c in mock_bot.send_message.call_args_list
            if c[0][0] == aggregator_config.telegram_admin_id
        ]
        assert len(admin_calls) == 1
        assert "Агрегатор упал" in admin_calls[0][0][1]

    async def test_run_cleanup_old_seen_called(self, pipeline, agg_queries):
        items = [_make_item()]
        pipeline._sources = {"fake": FakeSource(items)}

        with patch.object(agg_queries, "cleanup_old_seen", wraps=agg_queries.cleanup_old_seen) as mock_cleanup:
            await pipeline.run()
            mock_cleanup.assert_called_once_with(days=30)

    async def test_run_no_sources_returns_false(self, pipeline):
        pipeline._sources = {}
        # Also ensure _init_sources finds nothing
        with patch.object(pipeline, "_init_sources"):
            result = await pipeline.run()
        assert result is False

    async def test_run_saves_new_hashtags(self, pipeline, agg_queries, mock_llm):
        items = [_make_item()]
        pipeline._sources = {"fake": FakeSource(items)}

        await pipeline.run()

        tags = await agg_queries.get_all_hashtags()
        tag_names = [t.name for t in tags]
        assert "ml" in tag_names
        assert "новости" in tag_names
