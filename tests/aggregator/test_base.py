from __future__ import annotations

import pytest

from src.aggregator.sources.base import (
    SOURCE_REGISTRY,
    ContentItem,
    ContentSource,
    register_source,
)


@pytest.fixture(autouse=True)
def _clean_registry():
    """Save and restore SOURCE_REGISTRY around each test."""
    saved = dict(SOURCE_REGISTRY)
    yield
    SOURCE_REGISTRY.clear()
    SOURCE_REGISTRY.update(saved)


class TestRegisterSource:
    def test_decorator_adds_to_registry(self):
        @register_source("test_src")
        class _TestSource(ContentSource):
            name = "test_src"

            async def fetch(self) -> list[ContentItem]:
                return []

            async def health_check(self) -> bool:
                return True

        assert "test_src" in SOURCE_REGISTRY
        assert SOURCE_REGISTRY["test_src"] is _TestSource

    def test_decorator_returns_class_unchanged(self):
        @register_source("test_src2")
        class _TestSource2(ContentSource):
            name = "test_src2"

            async def fetch(self) -> list[ContentItem]:
                return []

            async def health_check(self) -> bool:
                return True

        assert _TestSource2.name == "test_src2"

    def test_multiple_sources_registered(self):
        @register_source("src_a")
        class _SrcA(ContentSource):
            name = "src_a"

            async def fetch(self) -> list[ContentItem]:
                return []

            async def health_check(self) -> bool:
                return True

        @register_source("src_b")
        class _SrcB(ContentSource):
            name = "src_b"

            async def fetch(self) -> list[ContentItem]:
                return []

            async def health_check(self) -> bool:
                return True

        assert "src_a" in SOURCE_REGISTRY
        assert "src_b" in SOURCE_REGISTRY


class TestContentItem:
    def test_dedup_key_format(self):
        item = ContentItem(
            source_name="my_source",
            title="Test",
            url="https://example.com/article",
            text="content",
        )
        assert item.dedup_key == "my_source:https://example.com/article"

    def test_dedup_key_different_sources(self):
        item_a = ContentItem(source_name="src_a", title="T", url="https://x.com/1", text="t")
        item_b = ContentItem(source_name="src_b", title="T", url="https://x.com/1", text="t")
        assert item_a.dedup_key != item_b.dedup_key

    def test_default_fields(self):
        item = ContentItem(source_name="s", title="T", url="https://x.com", text="t")
        assert item.language == "en"
        assert item.tags == []
        assert item.meta == {}
        assert item.fetched_at is not None


class TestContentSourceABC:
    def test_cannot_instantiate_without_fetch(self):
        with pytest.raises(TypeError):

            class _Incomplete(ContentSource):
                async def health_check(self) -> bool:
                    return True

            _Incomplete()  # type: ignore[abstract]

    def test_cannot_instantiate_without_health_check(self):
        with pytest.raises(TypeError):

            class _Incomplete(ContentSource):
                async def fetch(self) -> list[ContentItem]:
                    return []

            _Incomplete()  # type: ignore[abstract]

    def test_can_instantiate_complete_source(self):
        class _Complete(ContentSource):
            async def fetch(self) -> list[ContentItem]:
                return []

            async def health_check(self) -> bool:
                return True

        instance = _Complete()
        assert instance is not None

    async def test_default_close_is_noop(self):
        class _Complete(ContentSource):
            async def fetch(self) -> list[ContentItem]:
                return []

            async def health_check(self) -> bool:
                return True

        instance = _Complete()
        await instance.close()  # should not raise
