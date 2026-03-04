from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    telegram_bot_token: str
    telegram_channel_id: int
    telegram_admin_id: int

    openrouter_api_key: str

    custom_llm_api_url: str | None
    custom_llm_api_key: str | None
    custom_llm_model: str | None

    llm_request_delay: float
    llm_max_retries: int

    db_path: str

    # Aggregator settings
    aggregator_enabled: bool
    aggregator_enabled_sources: list[str]
    aggregator_schedule: str
    aggregator_tone: str

    @property
    def use_custom_llm(self) -> bool:
        return all([self.custom_llm_api_url, self.custom_llm_api_key, self.custom_llm_model])

    @classmethod
    def from_env(cls) -> Config:
        token = os.environ["TELEGRAM_BOT_TOKEN"]
        channel_id = int(os.environ["TELEGRAM_CHANNEL_ID"])
        admin_id = int(os.environ["TELEGRAM_ADMIN_ID"])
        openrouter_key = os.environ["OPENROUTER_API_KEY"]

        sources_raw = os.environ.get("AGGREGATOR_ENABLED_SOURCES", "")
        enabled_sources = [s.strip() for s in sources_raw.split(",") if s.strip()]

        return cls(
            telegram_bot_token=token,
            telegram_channel_id=channel_id,
            telegram_admin_id=admin_id,
            openrouter_api_key=openrouter_key,
            custom_llm_api_url=os.environ.get("CUSTOM_LLM_API_URL") or None,
            custom_llm_api_key=os.environ.get("CUSTOM_LLM_API_KEY") or None,
            custom_llm_model=os.environ.get("CUSTOM_LLM_MODEL") or None,
            llm_request_delay=float(os.environ.get("LLM_REQUEST_DELAY") or "2"),
            llm_max_retries=int(os.environ.get("LLM_MAX_RETRIES") or "3"),
            db_path=os.environ.get("DB_PATH") or "data/bot.db",
            aggregator_enabled=(os.environ.get("AGGREGATOR_ENABLED") or "false").lower()
            == "true",
            aggregator_enabled_sources=enabled_sources,
            aggregator_schedule=os.environ.get("AGGREGATOR_SCHEDULE") or "60",
            aggregator_tone=os.environ.get("AGGREGATOR_TONE") or "default",
        )
