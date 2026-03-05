from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from src.aggregator.sources.rss_example import RSSExampleSource, _strip_html

# ── Sample RSS XML ─────────────────────────────────────────────

_NOW_STRUCT = datetime.now(UTC).timetuple()

_SAMPLE_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
<channel>
  <title>Test Feed</title>
  <item>
    <title>Article One</title>
    <link>https://example.com/article-1</link>
    <description>First article summary</description>
    <pubDate>Mon, 01 Jan 2024 00:00:00 GMT</pubDate>
  </item>
  <item>
    <title>Article Two</title>
    <link>https://example.com/article-2</link>
    <description>&lt;p&gt;Second &lt;b&gt;bold&lt;/b&gt; article&lt;/p&gt;</description>
    <pubDate>Mon, 01 Jan 2024 00:00:00 GMT</pubDate>
  </item>
</channel>
</rss>"""


def _make_rss_with_dates(dates: list[datetime]) -> str:
    items = ""
    for i, dt in enumerate(dates):
        rfc = dt.strftime("%a, %d %b %Y %H:%M:%S GMT")
        items += f"""
  <item>
    <title>Item {i}</title>
    <link>https://example.com/item-{i}</link>
    <description>Content {i}</description>
    <pubDate>{rfc}</pubDate>
  </item>"""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>Test</title>{items}</channel></rss>"""


# ── Fixtures ───────────────────────────────────────────────────


@pytest.fixture
def rss_env(monkeypatch):
    monkeypatch.setenv("RSS_FEED_URLS", "https://feed1.example.com/rss")
    monkeypatch.setenv("RSS_MAX_ITEMS_PER_FEED", "10")
    monkeypatch.setenv("RSS_MAX_ITEMS_TOTAL", "50")
    monkeypatch.setenv("RSS_MAX_AGE_DAYS", "7")


@pytest.fixture
def rss_source(rss_env) -> RSSExampleSource:
    return RSSExampleSource()


# ── Tests ──────────────────────────────────────────────────────


class TestStripHtml:
    def test_removes_tags(self):
        assert _strip_html("<p>Hello <b>world</b></p>") == "Hello world"

    def test_decodes_entities(self):
        assert _strip_html("&amp; &lt; &gt;") == "& < >"

    def test_collapses_whitespace(self):
        assert _strip_html("  a   b  \n c  ") == "a b c"

    def test_empty_string(self):
        assert _strip_html("") == ""


class TestFetchParsesFeed:
    async def test_returns_content_items(self, rss_source):
        # Use recent dates so age filter passes
        now = datetime.now(UTC)
        rss_xml = _make_rss_with_dates([now, now - timedelta(hours=1)])

        mock_response = MagicMock(spec=httpx.Response)
        mock_response.text = rss_xml
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()

        rss_source._client = AsyncMock()
        rss_source._client.get = AsyncMock(return_value=mock_response)

        items = await rss_source.fetch()
        assert len(items) == 2
        assert items[0].source_name == "rss_example"
        assert items[0].url.startswith("https://example.com/item-")
        assert items[0].title.startswith("Item ")

    async def test_per_feed_error_does_not_break_others(self, monkeypatch):
        monkeypatch.setenv("RSS_FEED_URLS", "https://bad.example.com/rss,https://good.example.com/rss")
        monkeypatch.setenv("RSS_MAX_AGE_DAYS", "9999")
        source = RSSExampleSource()

        now = datetime.now(UTC)
        good_rss = _make_rss_with_dates([now])

        async def mock_get(url, **kwargs):
            if "bad" in url:
                raise httpx.ConnectError("Connection refused")
            resp = MagicMock(spec=httpx.Response)
            resp.text = good_rss
            resp.status_code = 200
            resp.raise_for_status = MagicMock()
            return resp

        source._client = AsyncMock()
        source._client.get = mock_get

        items = await source.fetch()
        assert len(items) == 1
        assert "good" not in items[0].source_name  # source_name is "rss_example"

    async def test_max_items_per_feed(self, monkeypatch):
        monkeypatch.setenv("RSS_FEED_URLS", "https://feed.example.com/rss")
        monkeypatch.setenv("RSS_MAX_ITEMS_PER_FEED", "2")
        monkeypatch.setenv("RSS_MAX_AGE_DAYS", "9999")
        source = RSSExampleSource()

        now = datetime.now(UTC)
        rss_xml = _make_rss_with_dates([now, now, now, now, now])

        mock_response = MagicMock(spec=httpx.Response)
        mock_response.text = rss_xml
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()

        source._client = AsyncMock()
        source._client.get = AsyncMock(return_value=mock_response)

        items = await source.fetch()
        assert len(items) == 2

    async def test_max_items_total(self, monkeypatch):
        monkeypatch.setenv("RSS_FEED_URLS", "https://f1.example.com/rss,https://f2.example.com/rss")
        monkeypatch.setenv("RSS_MAX_ITEMS_PER_FEED", "10")
        monkeypatch.setenv("RSS_MAX_ITEMS_TOTAL", "3")
        monkeypatch.setenv("RSS_MAX_AGE_DAYS", "9999")
        source = RSSExampleSource()

        now = datetime.now(UTC)
        rss_xml = _make_rss_with_dates([now, now, now, now, now])

        mock_response = MagicMock(spec=httpx.Response)
        mock_response.text = rss_xml
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()

        source._client = AsyncMock()
        source._client.get = AsyncMock(return_value=mock_response)

        items = await source.fetch()
        assert len(items) <= 3

    async def test_age_filtering(self, monkeypatch):
        monkeypatch.setenv("RSS_FEED_URLS", "https://feed.example.com/rss")
        monkeypatch.setenv("RSS_MAX_AGE_DAYS", "3")
        source = RSSExampleSource()

        now = datetime.now(UTC)
        old = now - timedelta(days=10)
        rss_xml = _make_rss_with_dates([now, old])

        mock_response = MagicMock(spec=httpx.Response)
        mock_response.text = rss_xml
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()

        source._client = AsyncMock()
        source._client.get = AsyncMock(return_value=mock_response)

        items = await source.fetch()
        assert len(items) == 1  # only the recent one

    async def test_html_stripped_from_content(self, rss_source):
        rss_xml = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>T</title>
<item>
  <title>&lt;b&gt;Bold Title&lt;/b&gt;</title>
  <link>https://example.com/html</link>
  <description>&lt;p&gt;Hello &lt;b&gt;world&lt;/b&gt;&lt;/p&gt;</description>
</item>
</channel></rss>"""

        mock_response = MagicMock(spec=httpx.Response)
        mock_response.text = rss_xml
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()

        rss_source._client = AsyncMock()
        rss_source._client.get = AsyncMock(return_value=mock_response)
        rss_source._max_age_days = 9999

        items = await rss_source.fetch()
        assert len(items) == 1
        assert "<b>" not in items[0].title
        assert "<p>" not in items[0].text


class TestHealthCheck:
    async def test_health_check_success(self, rss_source):
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200

        rss_source._client = AsyncMock()
        rss_source._client.head = AsyncMock(return_value=mock_response)

        result = await rss_source.health_check()
        assert result is True

    async def test_health_check_failure(self, rss_source):
        rss_source._client = AsyncMock()
        rss_source._client.head = AsyncMock(side_effect=httpx.ConnectError("fail"))

        result = await rss_source.health_check()
        assert result is False

    async def test_health_check_no_feeds(self, monkeypatch):
        monkeypatch.setenv("RSS_FEED_URLS", "")
        source = RSSExampleSource()

        result = await source.health_check()
        assert result is False

    async def test_health_check_server_error(self, rss_source):
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 500

        rss_source._client = AsyncMock()
        rss_source._client.head = AsyncMock(return_value=mock_response)

        result = await rss_source.health_check()
        assert result is False
