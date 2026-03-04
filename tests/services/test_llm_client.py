from unittest.mock import AsyncMock, MagicMock

import pytest

from src.config import Config
from src.services.llm_client import _OPENROUTER_FREE_MODEL, _OPENROUTER_URL, LLMClient


class TestLLMClientOpenRouter:
    async def test_complete_with_openrouter(self, config: Config):
        client = LLMClient(config)

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "LLM response text"}}]
        }
        mock_response.raise_for_status = MagicMock()

        client._client = AsyncMock()
        client._client.post = AsyncMock(return_value=mock_response)

        result = await client.complete("system prompt", "user prompt")

        assert result == "LLM response text"

        call_args = client._client.post.call_args
        assert call_args[0][0] == _OPENROUTER_URL
        payload = call_args[1]["json"]
        assert payload["model"] == _OPENROUTER_FREE_MODEL
        assert payload["messages"][0]["content"] == "system prompt"
        assert payload["messages"][1]["content"] == "user prompt"

    async def test_complete_sends_auth_header(self, config: Config):
        client = LLMClient(config)

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "ok"}}]
        }
        mock_response.raise_for_status = MagicMock()

        client._client = AsyncMock()
        client._client.post = AsyncMock(return_value=mock_response)

        await client.complete("sys", "usr")

        headers = client._client.post.call_args[1]["headers"]
        assert headers["Authorization"] == f"Bearer {config.openrouter_api_key}"


class TestLLMClientCustom:
    async def test_complete_with_custom_llm(self, custom_llm_config: Config):
        client = LLMClient(custom_llm_config)

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "custom response"}}]
        }
        mock_response.raise_for_status = MagicMock()

        client._client = AsyncMock()
        client._client.post = AsyncMock(return_value=mock_response)

        result = await client.complete("sys", "usr")

        assert result == "custom response"

        call_args = client._client.post.call_args
        assert call_args[0][0] == custom_llm_config.custom_llm_api_url
        payload = call_args[1]["json"]
        assert payload["model"] == custom_llm_config.custom_llm_model
        headers = call_args[1]["headers"]
        assert headers["Authorization"] == f"Bearer {custom_llm_config.custom_llm_api_key}"


class TestLLMClientErrors:
    async def test_empty_choices_raises(self, config: Config):
        client = LLMClient(config)

        mock_response = MagicMock()
        mock_response.json.return_value = {"choices": []}
        mock_response.raise_for_status = MagicMock()

        client._client = AsyncMock()
        client._client.post = AsyncMock(return_value=mock_response)

        with pytest.raises(ValueError, match="empty choices"):
            await client.complete("sys", "usr")

    async def test_empty_content_raises(self, config: Config):
        client = LLMClient(config)

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": ""}}]
        }
        mock_response.raise_for_status = MagicMock()

        client._client = AsyncMock()
        client._client.post = AsyncMock(return_value=mock_response)

        with pytest.raises(ValueError, match="empty content"):
            await client.complete("sys", "usr")

    async def test_http_error_propagates(self, config: Config):
        import httpx

        client = LLMClient(config)

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock(
            side_effect=httpx.HTTPStatusError(
                "429", request=MagicMock(), response=MagicMock()
            )
        )

        client._client = AsyncMock()
        client._client.post = AsyncMock(return_value=mock_response)

        with pytest.raises(httpx.HTTPStatusError):
            await client.complete("sys", "usr")

    async def test_close(self, config: Config):
        client = LLMClient(config)
        client._client = AsyncMock()
        await client.close()
        client._client.aclose.assert_called_once()
