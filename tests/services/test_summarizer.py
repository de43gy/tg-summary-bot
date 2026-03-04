import json
from unittest.mock import AsyncMock

import pytest

from src.db.models import Hashtag
from src.services.summarizer import Summarizer, _build_user_prompt, _parse_response


class TestBuildUserPrompt:
    def test_with_hashtags(self):
        from datetime import datetime

        tags = [
            Hashtag(id=1, name="python", created_at=datetime.now()),
            Hashtag(id=2, name="asyncio", created_at=datetime.now()),
        ]
        prompt = _build_user_prompt("Article text here", tags)
        assert "Article text here" in prompt
        assert "python" in prompt
        assert "asyncio" in prompt
        assert "Существующие хештеги:" in prompt

    def test_without_hashtags(self):
        prompt = _build_user_prompt("Article text here", [])
        assert "Article text here" in prompt
        assert "Существующие хештеги:" not in prompt

    def test_article_text_included(self):
        prompt = _build_user_prompt("Конкретный текст статьи о Kubernetes", [])
        assert "Конкретный текст статьи о Kubernetes" in prompt


class TestParseResponse:
    def test_valid_json(self):
        raw = json.dumps({
            "title": "Заголовок",
            "summary": "Конспект статьи",
            "hashtags": ["python", "web"],
        })
        result = _parse_response(raw)
        assert result["title"] == "Заголовок"
        assert result["summary"] == "Конспект статьи"
        assert result["hashtags"] == ["python", "web"]

    def test_json_in_code_block(self):
        raw = '```json\n{"title": "Заголовок", "summary": "Текст", "hashtags": ["ai"]}\n```'
        result = _parse_response(raw)
        assert result["title"] == "Заголовок"
        assert result["hashtags"] == ["ai"]

    def test_json_in_code_block_no_lang(self):
        raw = '```\n{"title": "T", "summary": "S", "hashtags": ["x"]}\n```'
        result = _parse_response(raw)
        assert result["title"] == "T"

    def test_missing_title_raises(self):
        raw = json.dumps({"summary": "text", "hashtags": ["a"]})
        with pytest.raises(ValueError, match="title"):
            _parse_response(raw)

    def test_missing_summary_raises(self):
        raw = json.dumps({"title": "T", "hashtags": ["a"]})
        with pytest.raises(ValueError, match="summary"):
            _parse_response(raw)

    def test_missing_hashtags_raises(self):
        raw = json.dumps({"title": "T", "summary": "S"})
        with pytest.raises(ValueError, match="hashtags"):
            _parse_response(raw)

    def test_invalid_title_type_raises(self):
        raw = json.dumps({"title": 123, "summary": "S", "hashtags": ["a"]})
        with pytest.raises(ValueError, match="title"):
            _parse_response(raw)

    def test_invalid_json_raises(self):
        with pytest.raises(json.JSONDecodeError):
            _parse_response("not json at all")

    def test_json_with_whitespace(self):
        raw = '  \n  {"title": "T", "summary": "S", "hashtags": ["a"]}  \n  '
        result = _parse_response(raw)
        assert result["title"] == "T"


class TestSummarizer:
    async def test_summarize_calls_llm(self):
        mock_llm = AsyncMock()
        mock_llm.complete = AsyncMock(return_value=json.dumps({
            "title": "Тест",
            "summary": "Конспект тестовой статьи",
            "hashtags": ["testing"],
        }))

        summarizer = Summarizer(mock_llm)
        result = await summarizer.summarize("Some article text", [])

        assert result["title"] == "Тест"
        assert result["summary"] == "Конспект тестовой статьи"
        assert result["hashtags"] == ["testing"]
        mock_llm.complete.assert_called_once()

    async def test_summarize_truncates_long_text(self):
        mock_llm = AsyncMock()
        mock_llm.complete = AsyncMock(return_value=json.dumps({
            "title": "T", "summary": "S", "hashtags": ["a"],
        }))

        summarizer = Summarizer(mock_llm)
        long_text = "x" * 50_000
        await summarizer.summarize(long_text, [])

        call_args = mock_llm.complete.call_args
        user_prompt = call_args[0][1]
        assert "[Текст обрезан из-за ограничений]" in user_prompt

    async def test_summarize_passes_hashtags_to_prompt(self):
        from datetime import datetime

        mock_llm = AsyncMock()
        mock_llm.complete = AsyncMock(return_value=json.dumps({
            "title": "T", "summary": "S", "hashtags": ["python"],
        }))

        tags = [
            Hashtag(id=1, name="python", created_at=datetime.now()),
            Hashtag(id=2, name="devops", created_at=datetime.now()),
        ]

        summarizer = Summarizer(mock_llm)
        await summarizer.summarize("text", tags)

        call_args = mock_llm.complete.call_args
        user_prompt = call_args[0][1]
        assert "python" in user_prompt
        assert "devops" in user_prompt
