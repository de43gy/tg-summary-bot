import asyncio
import contextlib
import logging

from aiogram import Bot, Dispatcher

from src.aggregator.pipeline import ContentPipeline
from src.aggregator.scheduler import AggregatorScheduler
from src.aggregator.sources import load_sources
from src.bot.commands import set_bot_commands
from src.bot.handlers import router, setup_admin_filter
from src.config import Config
from src.db.database import Database
from src.db.queries import Queries
from src.queue.processor import QueueProcessor
from src.services.article_parser import close_http_client
from src.services.llm_client import LLMClient
from src.services.summarizer import Summarizer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def main() -> None:
    config = Config.from_env()

    # Database
    db = Database(config.db_path)
    await db.connect()
    queries = Queries(db)

    # Services
    llm_client = LLMClient(config)
    summarizer = Summarizer(llm_client)

    # Bot
    bot = Bot(token=config.telegram_bot_token)
    dp = Dispatcher()
    setup_admin_filter(config)
    dp.include_router(router)

    # Queue processor
    processor = QueueProcessor(config, queries, summarizer, bot)

    # Aggregator (optional)
    agg_scheduler: AggregatorScheduler | None = None
    agg_pipeline: ContentPipeline | None = None
    if config.aggregator_enabled:
        load_sources()
        agg_pipeline = ContentPipeline(config, queries, llm_client, bot)
        agg_scheduler = AggregatorScheduler(config, agg_pipeline)
        agg_scheduler.setup()
        logger.info("Aggregator configured with sources: %s", config.aggregator_enabled_sources)

    # Inject dependencies via dispatcher middleware data
    dp["queries"] = queries
    dp["pipeline"] = agg_pipeline

    bg_task: asyncio.Task[None] | None = None

    async def on_startup(bot_instance: Bot) -> None:
        nonlocal bg_task
        await set_bot_commands(bot_instance)
        bg_task = asyncio.create_task(processor.start_background_loop())
        if agg_scheduler is not None:
            agg_scheduler.start()
        logger.info("Bot started, background queue processor running")

    async def on_shutdown(bot_instance: Bot) -> None:
        if agg_scheduler is not None:
            agg_scheduler.stop()
        if agg_pipeline is not None:
            await agg_pipeline.close()
        processor.stop()
        if bg_task is not None:
            bg_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await bg_task
        await llm_client.close()
        await close_http_client()
        await db.close()
        logger.info("Bot stopped")

    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
