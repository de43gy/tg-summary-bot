from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

from src.aggregator.pipeline import ContentPipeline
from src.config import Config
from src.db.queries import Queries
from src.services.article_parser import extract_urls, normalize_url

logger = logging.getLogger(__name__)

router = Router()


def setup_admin_filter(config: Config) -> None:
    """Apply admin-only filter to all handlers on this router."""
    router.message.filter(
        F.chat.type == "private",
        F.from_user.id == config.telegram_admin_id,
    )


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    await message.answer(
        "Привет! Отправь мне ссылку на статью, и я сделаю подробный конспект "
        "и опубликую его в канал.\n\n"
        "Команды:\n"
        "/search #тег — поиск по хештегу\n"
        "/search слово — полнотекстовый поиск\n"
        "/stats — статистика\n"
        "/retry — повторить неудачные статьи\n"
        "/digest — запустить агрегатор вручную"
    )


@router.message(Command("stats"))
async def cmd_stats(message: Message, queries: Queries) -> None:
    stats = await queries.get_stats()
    await message.answer(
        f"Статистика:\n"
        f"Всего статей: {stats['total']}\n"
        f"Обработано: {stats['done']}\n"
        f"Ошибки: {stats['failed']}\n"
        f"Хештегов: {stats['tags']}"
    )


@router.message(Command("search"))
async def cmd_search(message: Message, queries: Queries) -> None:
    args = (message.text or "").split(maxsplit=1)
    if len(args) < 2 or not args[1].strip():
        await message.answer("Использование: /search #тег или /search ключевое_слово")
        return

    query = args[1].strip()

    if query.startswith("#"):
        articles = await queries.search_articles_by_hashtag(query)
    else:
        articles = await queries.search_articles_by_summary(query)

    if not articles:
        await message.answer("Ничего не найдено.")
        return

    lines: list[str] = []
    for a in articles:
        title = a.title or "Без названия"
        lines.append(f"[{a.id}] {title}\n{a.url}")

    await message.answer("\n\n".join(lines))


@router.message(Command("retry"))
async def cmd_retry(message: Message, queries: Queries) -> None:
    args = (message.text or "").split(maxsplit=1)

    if len(args) >= 2 and args[1].strip().isdigit():
        article_id = int(args[1].strip())
        article = await queries.get_article_by_id(article_id)
        if not article:
            await message.answer(f"Статья с ID {article_id} не найдена.")
            return
        if article.status != "failed":
            await message.answer(
                f"Статья {article_id} не в статусе failed (текущий: {article.status})."
            )
            return
        await queries.reset_article_for_retry(article_id)
        await message.answer(f"Статья {article_id} поставлена в очередь на повторную обработку.")
    else:
        failed = await queries.get_failed_articles()
        if not failed:
            await message.answer("Нет статей с ошибками.")
            return
        for a in failed:
            await queries.reset_article_for_retry(a.id)
        await message.answer(f"Поставлено в очередь на повторную обработку: {len(failed)} статей.")


@router.message(Command("digest"))
async def cmd_digest(message: Message, pipeline: ContentPipeline | None) -> None:
    if pipeline is None:
        await message.answer("Агрегатор не включён. Установите AGGREGATOR_ENABLED=true.")
        return

    await message.answer("Запускаю агрегатор...")
    try:
        result = await pipeline.run()
        if result:
            await message.answer("Дайджест опубликован.")
        else:
            await message.answer("Нет новых материалов.")
    except Exception as exc:
        logger.exception("Manual digest run failed")
        await message.answer(f"Ошибка агрегатора: {exc}")


@router.message()
async def handle_message(message: Message, queries: Queries) -> None:
    """Handle regular DM messages -- extract URLs and save to DB for background processing."""
    text = message.text or message.caption or ""
    urls = extract_urls(text)

    if not urls:
        return  # silently ignore non-URL messages

    for url in urls:
        normalized = normalize_url(url)

        # Check for duplicates
        existing = await queries.get_article_by_normalized_url(normalized)
        if existing:
            if existing.status == "done":
                await message.answer(f"Эта статья уже обработана: {url}")
            elif existing.status in ("pending", "processing"):
                await message.answer(f"Эта статья уже в очереди: {url}")
            else:
                await message.answer(
                    f"Эта статья ранее не удалась. Используйте /retry {existing.id}"
                )
            continue

        await queries.create_article(url, normalized, chat_id=message.chat.id)
        await message.answer(f"Статья добавлена в очередь: {url}")
