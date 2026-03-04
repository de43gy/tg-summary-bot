"""
RSS source connector.

To enable:
1. Add "rss_example" to AGGREGATOR_ENABLED_SOURCES in .env
2. Set RSS_FEED_URLS to comma-separated list of feed URLs

Optional env vars:
- RSS_MAX_ITEMS_PER_FEED (default 10) — max items from each individual feed
- RSS_MAX_ITEMS_TOTAL (default 50) — max total items returned across all feeds
- RSS_MAX_AGE_DAYS (default 7) — skip entries older than N days
"""

from __future__ import annotations

import logging
import os
import re
from calendar import timegm
from datetime import UTC, datetime, timedelta
from html import unescape
from time import struct_time

import feedparser
import httpx

from src.aggregator.sources.base import ContentItem, ContentSource, register_source

logger = logging.getLogger(__name__)

_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")


def _strip_html(html: str) -> str:
    """Strip HTML tags and decode entities, returning clean text."""
    text = _TAG_RE.sub(" ", html)
    text = unescape(text)
    return _WHITESPACE_RE.sub(" ", text).strip()


def _parse_entry_time(entry: dict[str, object]) -> datetime | None:
    """Extract published or updated time from a feedparser entry."""
    for field in ("published_parsed", "updated_parsed"):
        parsed: struct_time | None = entry.get(field)  # type: ignore[assignment]
        if parsed is not None:
            try:
                return datetime.fromtimestamp(timegm(parsed), tz=UTC)
            except Exception:
                continue
    return None


@register_source("rss_example")
class RSSExampleSource(ContentSource):
    name = "rss_example"

    def __init__(self) -> None:
        self._feed_urls = [
            u.strip() for u in os.environ.get("RSS_FEED_URLS", "").split(",") if u.strip()
        ]
        self._max_per_feed = int(os.environ.get("RSS_MAX_ITEMS_PER_FEED", "10"))
        self._max_total = int(os.environ.get("RSS_MAX_ITEMS_TOTAL", "50"))
        self._max_age_days = int(os.environ.get("RSS_MAX_AGE_DAYS", "7"))
        self._client = httpx.AsyncClient(timeout=30.0)

    async def fetch(self) -> list[ContentItem]:
        items: list[ContentItem] = []
        cutoff = datetime.now(UTC) - timedelta(days=self._max_age_days)

        logger.info("RSS: checking %d feed(s)", len(self._feed_urls))

        for feed_url in self._feed_urls:
            feed_items = await self._fetch_single_feed(feed_url, cutoff)
            items.extend(feed_items)

            if len(items) >= self._max_total:
                items = items[: self._max_total]
                logger.info("RSS: reached total limit of %d items, stopping", self._max_total)
                break

        logger.info(
            "RSS: collected %d item(s) total from %d feed(s)", len(items), len(self._feed_urls)
        )
        return items

    async def _fetch_single_feed(self, feed_url: str, cutoff: datetime) -> list[ContentItem]:
        """Fetch and parse a single RSS feed. Returns empty list on failure."""
        collected: list[ContentItem] = []
        try:
            resp = await self._client.get(feed_url)
            resp.raise_for_status()
            feed = feedparser.parse(resp.text)

            for entry in feed.entries:
                if len(collected) >= self._max_per_feed:
                    break

                entry_time = _parse_entry_time(entry)
                if entry_time is not None and entry_time < cutoff:
                    continue

                link: str = entry.get("link", "")
                if not link:
                    continue

                title: str = entry.get("title", "")
                summary: str = entry.get("summary", "")
                content_blocks: list[dict[str, str]] = entry.get("content", [])
                raw_content = content_blocks[0].get("value", "") if content_blocks else ""
                text = _strip_html(raw_content or summary)

                tags: list[str] = list(
                    {t.get("term", "") for t in entry.get("tags", []) if t.get("term")}
                )

                collected.append(
                    ContentItem(
                        source_name=self.name,
                        title=_strip_html(title),
                        url=link,
                        text=text[:5000],
                        language="en",
                        tags=tags,
                    )
                )

            logger.info("RSS: feed %s — %d item(s) collected", feed_url, len(collected))

        except Exception:
            logger.exception("RSS: failed to fetch feed: %s", feed_url)

        return collected

    async def health_check(self) -> bool:
        if not self._feed_urls:
            return False
        try:
            resp = await self._client.head(self._feed_urls[0])
            return resp.status_code < 400
        except Exception:
            return False

    async def close(self) -> None:
        await self._client.aclose()
