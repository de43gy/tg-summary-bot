import pytest

from src.config import Config
from src.db.database import Database
from src.db.queries import Queries


@pytest.fixture
def config() -> Config:
    return Config(
        telegram_bot_token="test-token",
        telegram_channel_id=-1001234567890,
        telegram_admin_id=123456789,
        openrouter_api_key="test-openrouter-key",
        custom_llm_api_url=None,
        custom_llm_api_key=None,
        custom_llm_model=None,
        llm_request_delay=0.01,
        llm_max_retries=3,
        db_path=":memory:",
        aggregator_enabled=False,
        aggregator_enabled_sources=[],
        aggregator_schedule="60",
        aggregator_tone="default",
    )


@pytest.fixture
def custom_llm_config() -> Config:
    return Config(
        telegram_bot_token="test-token",
        telegram_channel_id=-1001234567890,
        telegram_admin_id=123456789,
        openrouter_api_key="test-openrouter-key",
        custom_llm_api_url="https://custom-llm.example.com/v1/chat/completions",
        custom_llm_api_key="test-custom-key",
        custom_llm_model="custom-model-v1",
        llm_request_delay=0.01,
        llm_max_retries=3,
        db_path=":memory:",
        aggregator_enabled=False,
        aggregator_enabled_sources=[],
        aggregator_schedule="60",
        aggregator_tone="default",
    )


@pytest.fixture
async def db() -> Database:
    database = Database(":memory:")
    await database.connect()
    yield database
    await database.close()


@pytest.fixture
async def queries(db: Database) -> Queries:
    return Queries(db)
