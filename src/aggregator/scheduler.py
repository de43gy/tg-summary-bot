from __future__ import annotations

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from src.aggregator.pipeline import ContentPipeline
from src.config import Config

logger = logging.getLogger(__name__)


class AggregatorScheduler:
    def __init__(self, config: Config, pipeline: ContentPipeline) -> None:
        self._config = config
        self._pipeline = pipeline
        self._scheduler = AsyncIOScheduler()

    def setup(self) -> None:
        schedule_str = self._config.aggregator_schedule

        if schedule_str.startswith("cron:"):
            cron_expr = schedule_str[5:].strip()
            parts = cron_expr.split()
            trigger = CronTrigger(
                minute=parts[0] if len(parts) > 0 else "*",
                hour=parts[1] if len(parts) > 1 else "*",
                day=parts[2] if len(parts) > 2 else "*",
                month=parts[3] if len(parts) > 3 else "*",
                day_of_week=parts[4] if len(parts) > 4 else "*",
            )
            logger.info("Aggregator scheduled with cron: %s", cron_expr)
        else:
            minutes = int(schedule_str)
            trigger = IntervalTrigger(minutes=minutes)
            logger.info("Aggregator scheduled every %d minutes", minutes)

        self._scheduler.add_job(
            self._run_pipeline,
            trigger=trigger,
            id="aggregator_pipeline",
            replace_existing=True,
            max_instances=1,
        )

    async def _run_pipeline(self) -> None:
        logger.info("Aggregator pipeline triggered by scheduler")
        try:
            await self._pipeline.run()
        except Exception:
            logger.exception("Aggregator pipeline failed")

    def start(self) -> None:
        self._scheduler.start()
        logger.info("Aggregator scheduler started")

    def stop(self) -> None:
        self._scheduler.shutdown(wait=False)
        logger.info("Aggregator scheduler stopped")
