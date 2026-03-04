from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from src.aggregator.scheduler import AggregatorScheduler
from src.config import Config


@pytest.fixture
def mock_pipeline():
    return AsyncMock()


def _make_config(schedule: str = "60") -> Config:
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
        aggregator_schedule=schedule,
        aggregator_tone="default",
    )


class TestSchedulerSetup:
    def test_interval_schedule(self, mock_pipeline):
        config = _make_config("60")
        scheduler = AggregatorScheduler(config, mock_pipeline)
        scheduler.setup()

        job = scheduler._scheduler.get_job("aggregator_pipeline")
        assert job is not None
        assert isinstance(job.trigger, IntervalTrigger)

    def test_cron_schedule(self, mock_pipeline):
        config = _make_config("cron:0 9 * * *")
        scheduler = AggregatorScheduler(config, mock_pipeline)
        scheduler.setup()

        job = scheduler._scheduler.get_job("aggregator_pipeline")
        assert job is not None
        assert isinstance(job.trigger, CronTrigger)

    def test_interval_different_values(self, mock_pipeline):
        config = _make_config("30")
        scheduler = AggregatorScheduler(config, mock_pipeline)
        scheduler.setup()

        job = scheduler._scheduler.get_job("aggregator_pipeline")
        assert job is not None
        assert isinstance(job.trigger, IntervalTrigger)


class TestSchedulerStartStop:
    async def test_start_and_stop(self, mock_pipeline):
        config = _make_config("60")
        scheduler = AggregatorScheduler(config, mock_pipeline)
        scheduler.setup()

        scheduler.start()
        assert scheduler._scheduler.running is True

        # shutdown(wait=False) is non-blocking; just verify no exception
        scheduler.stop()

    async def test_stop_without_start(self, mock_pipeline):
        from apscheduler.schedulers import SchedulerNotRunningError

        config = _make_config("60")
        scheduler = AggregatorScheduler(config, mock_pipeline)
        scheduler.setup()
        # Stopping without starting raises SchedulerNotRunningError
        with pytest.raises(SchedulerNotRunningError):
            scheduler.stop()
