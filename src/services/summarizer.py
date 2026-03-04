from __future__ import annotations

import json
import logging
import re
from typing import Any

from src.db.models import Hashtag
from src.services.llm_client import LLMClient

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """Ты — ассистент, составляющий подробные конспекты технических статей на русском языке.

Тебе будет дан текст статьи и список существующих хештегов.
Твоя задача:
1. Написать подробный конспект статьи на русском языке. Не тизер, а полноценный конспект, чтобы читатель мог не открывать оригинал. Пиши сухо, технично, без маркетинговой воды.
2. Предложить название статьи на русском (краткое и ёмкое).
3. Выбрать подходящие хештеги из существующего пула ИЛИ предложить новые (без #, маленькими буквами, одним словом или через_подчёркивание).

Ответ верни СТРОГО в формате JSON (и ничего кроме JSON):
{
  "title": "Название статьи",
  "summary": "Подробный конспект...",
  "hashtags": ["тег1", "тег2", "тег3"]
}

Правила:
- Конспект НА РУССКОМ, даже если оригинал на английском
- Конспект должен быть подробным: описывай ключевые концепции, подходы, инструменты, выводы
- Хештеги: от 2 до 5 штук, релевантные
- Если подходят существующие хештеги — используй их. Новые создавай только при необходимости
- Не добавляй символ # к хештегам в ответе
"""


def _build_user_prompt(article_text: str, existing_hashtags: list[Hashtag]) -> str:
    tag_list = ", ".join(h.name for h in existing_hashtags)
    hashtag_section = f"\n\nСуществующие хештеги: {tag_list}" if tag_list else ""

    return f"Текст статьи:\n\n{article_text}{hashtag_section}"


def parse_llm_json_response(raw: str) -> dict[str, Any]:
    """Parse LLM response as JSON. Strips markdown code fences if present."""
    cleaned = raw.strip()

    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", cleaned, re.DOTALL)
    if match:
        cleaned = match.group(1).strip()

    result: dict[str, Any] = json.loads(cleaned)
    return result


def _parse_response(raw: str) -> dict[str, Any]:
    """Parse LLM response as JSON with field validation for article summaries."""
    result = parse_llm_json_response(raw)

    if not isinstance(result.get("title"), str):
        raise ValueError("Missing or invalid 'title'")
    if not isinstance(result.get("summary"), str):
        raise ValueError("Missing or invalid 'summary'")
    if not isinstance(result.get("hashtags"), list):
        raise ValueError("Missing or invalid 'hashtags'")

    return result


class Summarizer:
    def __init__(self, llm_client: LLMClient) -> None:
        self._llm = llm_client

    async def summarize(
        self, article_text: str, existing_hashtags: list[Hashtag]
    ) -> dict[str, Any]:
        """Return dict with keys: title, summary, hashtags (list of str)."""
        # Truncate very long articles to avoid token limits
        max_chars = 30_000
        if len(article_text) > max_chars:
            article_text = article_text[:max_chars] + "\n\n[Текст обрезан из-за ограничений]"

        user_prompt = _build_user_prompt(article_text, existing_hashtags)
        raw_response = await self._llm.complete(_SYSTEM_PROMPT, user_prompt)
        return _parse_response(raw_response)
