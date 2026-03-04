from __future__ import annotations

import logging

import httpx

from src.config import Config

logger = logging.getLogger(__name__)

_OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
_OPENROUTER_FREE_MODEL = "openrouter/free"


class LLMClient:
    def __init__(self, config: Config) -> None:
        self._config = config
        self._client = httpx.AsyncClient(timeout=120.0)

    async def close(self) -> None:
        await self._client.aclose()

    async def complete(self, system_prompt: str, user_prompt: str) -> str:
        """Send a chat completion request and return the assistant message content."""
        if self._config.use_custom_llm:
            url = self._config.custom_llm_api_url
            api_key = self._config.custom_llm_api_key
            model = self._config.custom_llm_model
        else:
            url = _OPENROUTER_URL
            api_key = self._config.openrouter_api_key
            model = _OPENROUTER_FREE_MODEL

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.3,
        }

        if url is None:
            raise ValueError("LLM API URL is not configured")
        response = await self._client.post(url, json=payload, headers=headers)
        response.raise_for_status()
        data: dict[str, object] = response.json()

        choices = data.get("choices", [])
        if not isinstance(choices, list) or not choices:
            raise ValueError("LLM returned empty choices")

        message = choices[0]
        if not isinstance(message, dict):
            raise ValueError("LLM returned invalid choice format")
        msg_data = message.get("message", {})
        if not isinstance(msg_data, dict):
            raise ValueError("LLM returned invalid message format")
        content = msg_data.get("content", "")
        if not isinstance(content, str) or not content:
            raise ValueError("LLM returned empty content")

        return content
