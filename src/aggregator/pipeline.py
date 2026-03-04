from __future__ import annotations

import asyncio
import hashlib
import logging
from dataclasses import dataclass, field
from pathlib import Path

from aiogram import Bot
from jinja2 import Environment, FileSystemLoader

from src.aggregator.sources.base import SOURCE_REGISTRY, ContentItem, ContentSource
from src.config import Config
from src.db.queries import Queries
from src.services.formatter import format_channel_post
from src.services.llm_client import LLMClient
from src.services.summarizer import parse_llm_json_response

logger = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).parent / "prompts"

_DIGEST_SYSTEM_PROMPT = """Ты — ассистент, составляющий дайджест-посты для Telegram-канала на русском языке.
Тебе будет дан набор материалов из разных источников (имиджборды, форумы, RSS и т.д.)
и инструкция по тону.

Твоя задача:
1. Написать обзорный пост-дайджест на русском языке, объединяющий ключевые находки.
2. Предложить краткий заголовок на русском.
3. Выбрать подходящие хештеги из существующего пула или предложить новые.

Ответ верни СТРОГО в формате JSON:
{
  "title": "Заголовок дайджеста",
  "summary": "Текст дайджеста...",
  "hashtags": ["тег1", "тег2"]
}

Правила:
- Пиши НА РУССКОМ, даже если материалы на других языках
- Указывай откуда информация (название источника, борда, сайт)
- Если есть интересные ссылки — упоминай их
- Хештеги: от 2 до 5 штук, релевантные
"""


@dataclass
class PipelineContext:
    items: list[ContentItem] = field(default_factory=list)
    new_items: list[ContentItem] = field(default_factory=list)
    generated_title: str = ""
    generated_summary: str = ""
    generated_hashtags: list[str] = field(default_factory=list)
    post_text: str = ""
    source_urls: list[str] = field(default_factory=list)


class ContentPipeline:
    def __init__(
        self,
        config: Config,
        queries: Queries,
        llm_client: LLMClient,
        bot: Bot,
    ) -> None:
        self._config = config
        self._queries = queries
        self._llm = llm_client
        self._bot = bot
        self._sources: dict[str, ContentSource] = {}
        self._jinja_env = Environment(
            loader=FileSystemLoader(str(_PROMPTS_DIR)),
            autoescape=False,
        )

    def _init_sources(self) -> None:
        enabled = self._config.aggregator_enabled_sources
        for name, cls in SOURCE_REGISTRY.items():
            if name in enabled:
                try:
                    self._sources[name] = cls()
                    logger.info("Initialized source: %s", name)
                except Exception:
                    logger.exception("Failed to init source: %s", name)

    async def run(self) -> bool:
        if not self._sources:
            self._init_sources()

        if not self._sources:
            logger.warning("No sources configured, skipping pipeline run")
            return False

        ctx = PipelineContext()

        try:
            await self._stage_collect(ctx)
            if not ctx.items:
                logger.info("No items collected from any source")
                return False

            await self._stage_deduplicate(ctx)
            if not ctx.new_items:
                logger.info("All items already seen, nothing new")
                return False

            await self._stage_generate(ctx)
            if not ctx.generated_summary:
                logger.error("LLM generation failed, aborting")
                return False

            self._stage_format(ctx)

            await self._stage_publish(ctx)
            return True
        except Exception as exc:
            logger.exception("Pipeline run failed")
            try:
                await self._bot.send_message(
                    self._config.telegram_admin_id,
                    f"\u26a0\ufe0f \u0410\u0433\u0440\u0435\u0433\u0430\u0442\u043e\u0440 \u0443\u043f\u0430\u043b: {exc}",
                )
            except Exception:
                logger.exception("Failed to send admin notification")
            raise
        finally:
            try:
                deleted = await self._queries.cleanup_old_seen(days=30)
                if deleted:
                    logger.info("Cleaned up %d old entries from content_seen", deleted)
            except Exception:
                logger.exception("Failed to cleanup old seen entries")

    async def _stage_collect(self, ctx: PipelineContext) -> None:
        names = list(self._sources.keys())
        results = await asyncio.gather(
            *(self._sources[n].fetch() for n in names),
            return_exceptions=True,
        )
        for name, result in zip(names, results, strict=True):
            if isinstance(result, BaseException):
                logger.exception("Source %s failed during fetch: %s", name, result)
            else:
                ctx.items.extend(result)
                logger.info("Collected %d items from %s", len(result), name)

    async def _stage_deduplicate(self, ctx: PipelineContext) -> None:
        for item in ctx.items:
            content_hash = hashlib.sha256(item.dedup_key.encode()).hexdigest()
            seen = await self._queries.is_content_seen(content_hash)
            if not seen:
                await self._queries.mark_content_seen(content_hash, item.source_name, item.url)
                ctx.new_items.append(item)
            else:
                logger.debug("Skipping duplicate: %s", item.url)

    async def _stage_generate(self, ctx: PipelineContext) -> None:
        items_text = self._render_items_for_prompt(ctx.new_items)
        existing_hashtags = await self._queries.get_top_hashtags(limit=50)
        tag_list = ", ".join(h.name for h in existing_hashtags)

        tone = self._config.aggregator_tone
        try:
            template = self._jinja_env.get_template(f"digest_{tone}.j2")
            user_prompt = template.render(items_text=items_text, tag_list=tag_list)
        except Exception:
            user_prompt = (
                f"Материалы для дайджеста:\n\n{items_text}\n\n"
                f"Существующие хештеги: {tag_list}\n\n"
                f"Тон: {tone}"
            )

        try:
            raw = await self._llm.complete(_DIGEST_SYSTEM_PROMPT, user_prompt)
            result = parse_llm_json_response(raw)

            ctx.generated_title = result.get("title", "Дайджест")
            ctx.generated_summary = result.get("summary", "")
            ctx.generated_hashtags = result.get("hashtags", [])
            ctx.source_urls = [item.url for item in ctx.new_items]
        except Exception:
            logger.exception("Failed to generate digest via LLM")

    def _stage_format(self, ctx: PipelineContext) -> None:
        links_section = "\n".join(f"• {url}" for url in ctx.source_urls[:10])
        summary_with_links = ctx.generated_summary
        if links_section:
            summary_with_links += f"\n\nИсточники:\n{links_section}"

        ctx.post_text = format_channel_post(
            title=ctx.generated_title,
            summary=summary_with_links,
            hashtags=ctx.generated_hashtags,
            original_url="",
        )

    async def _stage_publish(self, ctx: PipelineContext) -> None:
        try:
            await self._bot.send_message(
                self._config.telegram_channel_id,
                ctx.post_text,
                disable_web_page_preview=True,
            )
            logger.info("Digest published to channel")

            for tag_name in ctx.generated_hashtags:
                await self._queries.get_or_create_hashtag(tag_name)
        except Exception:
            logger.exception("Failed to publish digest")

    @staticmethod
    def _render_items_for_prompt(items: list[ContentItem]) -> str:
        parts: list[str] = []
        for i, item in enumerate(items, 1):
            part = (
                f"[{i}] Источник: {item.source_name}\n"
                f"Заголовок: {item.title}\n"
                f"URL: {item.url}\n"
                f"Язык: {item.language}\n"
                f"Текст:\n{item.text[:3000]}\n"
            )
            parts.append(part)
        return "\n---\n".join(parts)

    async def close(self) -> None:
        for source in self._sources.values():
            await source.close()
