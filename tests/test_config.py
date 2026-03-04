import os
from unittest.mock import patch

import pytest

from src.config import Config


class TestConfigFromEnv:
    def test_from_env_with_required_vars(self):
        env = {
            "TELEGRAM_BOT_TOKEN": "123:ABC",
            "TELEGRAM_CHANNEL_ID": "-1001234567890",
            "TELEGRAM_ADMIN_ID": "987654321",
            "OPENROUTER_API_KEY": "or-key-123",
        }
        with patch.dict(os.environ, env, clear=True):
            cfg = Config.from_env()

        assert cfg.telegram_bot_token == "123:ABC"
        assert cfg.telegram_channel_id == -1001234567890
        assert cfg.telegram_admin_id == 987654321
        assert cfg.openrouter_api_key == "or-key-123"
        assert cfg.custom_llm_api_url is None
        assert cfg.custom_llm_api_key is None
        assert cfg.custom_llm_model is None
        assert cfg.llm_request_delay == 2.0
        assert cfg.llm_max_retries == 3
        assert cfg.db_path == "data/bot.db"

    def test_from_env_with_custom_llm(self):
        env = {
            "TELEGRAM_BOT_TOKEN": "123:ABC",
            "TELEGRAM_CHANNEL_ID": "-100999",
            "TELEGRAM_ADMIN_ID": "111",
            "OPENROUTER_API_KEY": "or-key",
            "CUSTOM_LLM_API_URL": "https://llm.example.com/v1",
            "CUSTOM_LLM_API_KEY": "custom-key",
            "CUSTOM_LLM_MODEL": "gpt-4o",
            "LLM_REQUEST_DELAY": "5",
            "LLM_MAX_RETRIES": "1",
            "DB_PATH": "/tmp/test.db",
        }
        with patch.dict(os.environ, env, clear=True):
            cfg = Config.from_env()

        assert cfg.custom_llm_api_url == "https://llm.example.com/v1"
        assert cfg.custom_llm_api_key == "custom-key"
        assert cfg.custom_llm_model == "gpt-4o"
        assert cfg.llm_request_delay == 5.0
        assert cfg.llm_max_retries == 1
        assert cfg.db_path == "/tmp/test.db"

    def test_from_env_missing_required_var(self):
        env = {
            "TELEGRAM_CHANNEL_ID": "-100999",
            "TELEGRAM_ADMIN_ID": "111",
            "OPENROUTER_API_KEY": "or-key",
        }
        with patch.dict(os.environ, env, clear=True), pytest.raises(KeyError):
            Config.from_env()


class TestConfigProperties:
    def test_use_custom_llm_true(self, custom_llm_config: Config):
        assert custom_llm_config.use_custom_llm is True

    def test_use_custom_llm_false(self, config: Config):
        assert config.use_custom_llm is False

    def test_use_custom_llm_partial(self):
        cfg = Config(
            telegram_bot_token="t",
            telegram_channel_id=-1,
            telegram_admin_id=1,
            openrouter_api_key="k",
            custom_llm_api_url="https://example.com",
            custom_llm_api_key=None,
            custom_llm_model="model",
            llm_request_delay=2,
            llm_max_retries=3,
            db_path=":memory:",
            aggregator_enabled=False,
            aggregator_enabled_sources=[],
            aggregator_schedule="60",
            aggregator_tone="default",
        )
        assert cfg.use_custom_llm is False

    def test_config_is_frozen(self, config: Config):
        with pytest.raises(AttributeError):
            config.telegram_bot_token = "new-token"  # type: ignore[misc]
