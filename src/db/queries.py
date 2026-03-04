from __future__ import annotations

from datetime import UTC, datetime

import aiosqlite

from src.db.database import Database
from src.db.models import Article, Hashtag


def _row_to_article(row: aiosqlite.Row) -> Article:
    return Article(
        id=row["id"],
        url=row["url"],
        url_normalized=row["url_normalized"],
        title=row["title"],
        summary=row["summary"],
        status=row["status"],
        error_message=row["error_message"],
        channel_message_id=row["channel_message_id"],
        chat_id=row["chat_id"],
        retry_count=row["retry_count"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _row_to_hashtag(row: aiosqlite.Row) -> Hashtag:
    return Hashtag(
        id=row["id"],
        name=row["name"],
        created_at=row["created_at"],
    )


class Queries:
    def __init__(self, db: Database) -> None:
        self._db = db

    # ── Articles ──────────────────────────────────────────────

    async def get_article_by_normalized_url(self, url_normalized: str) -> Article | None:
        cursor = await self._db.conn.execute(
            "SELECT * FROM articles WHERE url_normalized = ?", (url_normalized,)
        )
        row = await cursor.fetchone()
        return _row_to_article(row) if row else None

    async def get_article_by_id(self, article_id: int) -> Article | None:
        cursor = await self._db.conn.execute("SELECT * FROM articles WHERE id = ?", (article_id,))
        row = await cursor.fetchone()
        return _row_to_article(row) if row else None

    async def create_article(
        self, url: str, url_normalized: str, chat_id: int | None = None
    ) -> Article:
        cursor = await self._db.conn.execute(
            "INSERT INTO articles (url, url_normalized, chat_id) VALUES (?, ?, ?)",
            (url, url_normalized, chat_id),
        )
        await self._db.conn.commit()
        article = await self.get_article_by_id(cursor.lastrowid)  # type: ignore[arg-type]
        assert article is not None  # just inserted
        return article

    async def update_article_status(
        self,
        article_id: int,
        status: str,
        *,
        title: str | None = None,
        summary: str | None = None,
        error_message: str | None = None,
        channel_message_id: int | None = None,
    ) -> None:
        # updated_at is handled automatically by the DB trigger
        fields: list[str] = ["status = ?"]
        params: list[object] = [status]

        if title is not None:
            fields.append("title = ?")
            params.append(title)
        if summary is not None:
            fields.append("summary = ?")
            params.append(summary)
        if error_message is not None:
            fields.append("error_message = ?")
            params.append(error_message)
        if channel_message_id is not None:
            fields.append("channel_message_id = ?")
            params.append(channel_message_id)

        params.append(article_id)
        sql = f"UPDATE articles SET {', '.join(fields)} WHERE id = ?"
        await self._db.conn.execute(sql, params)
        await self._db.conn.commit()

    async def get_pending_articles(self) -> list[Article]:
        cursor = await self._db.conn.execute(
            "SELECT * FROM articles WHERE status IN ('pending', 'processing') ORDER BY created_at"
        )
        rows = await cursor.fetchall()
        return [_row_to_article(r) for r in rows]

    async def get_failed_articles(self) -> list[Article]:
        cursor = await self._db.conn.execute(
            "SELECT * FROM articles WHERE status = 'failed' ORDER BY created_at"
        )
        rows = await cursor.fetchall()
        return [_row_to_article(r) for r in rows]

    async def reset_article_for_retry(self, article_id: int) -> None:
        # updated_at is handled automatically by the DB trigger
        await self._db.conn.execute(
            "UPDATE articles SET status = 'pending', error_message = NULL WHERE id = ?",
            (article_id,),
        )
        await self._db.conn.commit()

    async def increment_retry_count(self, article_id: int) -> int:
        """Increment retry_count and return the new value."""
        await self._db.conn.execute(
            "UPDATE articles SET retry_count = retry_count + 1 WHERE id = ?",
            (article_id,),
        )
        await self._db.conn.commit()
        article = await self.get_article_by_id(article_id)
        return article.retry_count if article else 0

    async def search_articles_by_summary(self, keyword: str) -> list[Article]:
        # Escape LIKE special characters in user input
        escaped = keyword.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        cursor = await self._db.conn.execute(
            "SELECT * FROM articles WHERE status = 'done' AND summary LIKE ? ESCAPE '\\' ORDER BY created_at DESC LIMIT 20",
            (f"%{escaped}%",),
        )
        rows = await cursor.fetchall()
        return [_row_to_article(r) for r in rows]

    async def get_stats(self) -> dict[str, int]:
        cursor = await self._db.conn.execute(
            """
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN status = 'done' THEN 1 ELSE 0 END) AS done,
                SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) AS failed,
                (SELECT COUNT(*) FROM hashtags) AS tags
            FROM articles
            """
        )
        row = await cursor.fetchone()
        if row is None:
            return {"total": 0, "done": 0, "failed": 0, "tags": 0}
        return {
            "total": row["total"],
            "done": row["done"],
            "failed": row["failed"],
            "tags": row["tags"],
        }

    # ── Hashtags ──────────────────────────────────────────────

    async def get_all_hashtags(self) -> list[Hashtag]:
        cursor = await self._db.conn.execute("SELECT * FROM hashtags ORDER BY name")
        rows = await cursor.fetchall()
        return [_row_to_hashtag(r) for r in rows]

    async def get_top_hashtags(self, limit: int = 50) -> list[Hashtag]:
        """Return the most-used hashtags, capped at `limit`."""
        cursor = await self._db.conn.execute(
            """
            SELECT h.*, COUNT(ah.article_id) AS usage_count
            FROM hashtags h
            LEFT JOIN article_hashtags ah ON h.id = ah.hashtag_id
            GROUP BY h.id
            ORDER BY usage_count DESC, h.created_at DESC
            LIMIT ?
            """,
            (limit,),
        )
        rows = await cursor.fetchall()
        return [_row_to_hashtag(r) for r in rows]

    async def get_or_create_hashtag(self, name: str) -> Hashtag:
        name = name.lower().strip().lstrip("#")
        cursor = await self._db.conn.execute("SELECT * FROM hashtags WHERE name = ?", (name,))
        row = await cursor.fetchone()
        if row:
            return _row_to_hashtag(row)

        cursor = await self._db.conn.execute("INSERT INTO hashtags (name) VALUES (?)", (name,))
        await self._db.conn.commit()
        return Hashtag(id=cursor.lastrowid, name=name, created_at=datetime.now(UTC))  # type: ignore[arg-type]

    async def link_article_hashtags(self, article_id: int, hashtag_ids: list[int]) -> None:
        await self._db.conn.executemany(
            "INSERT OR IGNORE INTO article_hashtags (article_id, hashtag_id) VALUES (?, ?)",
            [(article_id, hid) for hid in hashtag_ids],
        )
        await self._db.conn.commit()

    # ── Content dedup (aggregator) ─────────────────────────

    async def is_content_seen(self, content_hash: str) -> bool:
        cursor = await self._db.conn.execute(
            "SELECT 1 FROM content_seen WHERE content_hash = ?", (content_hash,)
        )
        return await cursor.fetchone() is not None

    async def mark_content_seen(self, content_hash: str, source_name: str, url: str) -> None:
        await self._db.conn.execute(
            "INSERT OR IGNORE INTO content_seen (content_hash, source_name, url) VALUES (?, ?, ?)",
            (content_hash, source_name, url),
        )
        await self._db.conn.commit()

    async def cleanup_old_seen(self, days: int = 30) -> int:
        cursor = await self._db.conn.execute(
            "DELETE FROM content_seen WHERE seen_at < datetime('now', ?)",
            (f"-{days} days",),
        )
        await self._db.conn.commit()
        return cursor.rowcount

    async def search_articles_by_hashtag(self, tag_name: str) -> list[Article]:
        tag_name = tag_name.lower().strip().lstrip("#")
        cursor = await self._db.conn.execute(
            """
            SELECT a.* FROM articles a
            JOIN article_hashtags ah ON a.id = ah.article_id
            JOIN hashtags h ON h.id = ah.hashtag_id
            WHERE h.name = ? AND a.status = 'done'
            ORDER BY a.created_at DESC LIMIT 20
            """,
            (tag_name,),
        )
        rows = await cursor.fetchall()
        return [_row_to_article(r) for r in rows]
