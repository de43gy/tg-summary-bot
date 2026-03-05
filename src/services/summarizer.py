from __future__ import annotations

import json
import logging
import re
from typing import Any

from src.db.models import Hashtag
from src.services.llm_client import LLMClient

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """Ты — ассистент, составляющий ПОЛНЫЕ конспекты статей на русском языке.

Цель: читатель прочитает твой конспект и ему НЕ НУЖНО будет открывать оригинал. Конспект должен заменить статью, а не рекламировать её.

Тебе будет дан текст статьи и список существующих хештегов.

Ответ верни СТРОГО в формате JSON (и ничего кроме JSON):
{
  "title": "Описательное название конспекта (не копируй заголовок статьи, перефразируй)",
  "summary": "Полный текст конспекта (структура описана ниже)",
  "commentary": "Критический комментарий (структура описана ниже)",
  "hashtags": ["тег1", "тег2"]
}

СТРУКТУРА КОНСПЕКТА (поле summary):

1. Суть статьи — 2-3 предложения, о чём статья и зачем её писали.

2. Основное содержание — самая большая часть. Разбей по логическим разделам.
   Для каждого раздела/темы/инструмента:
   - Что это, зачем нужно
   - Как работает (конкретика, параметры, примеры)
   - Практические детали: команды, конфиги, ссылки, цифры
   - Нюансы и подводные камни, о которых пишет автор

КРИТИЧЕСКИЙ КОММЕНТАРИЙ (поле commentary):
Твоя оценка по трём осям:
- Полезность: высокая/средняя/низкая — объясни почему
- Оригинальность: высокая/средняя/низкая — есть ли что-то новое vs пересказ известного
- Актуальность: насколько быстро устареет
Итого: 2-3 предложения — для кого статья полезна, для кого нет

ПРАВИЛА:
- Пиши НА РУССКОМ, даже если оригинал на английском
- Пиши сухо, технично, без воды и маркетинга
- НЕ ПИШИ фразы типа «автор рассказывает о...», «в статье описывается...» — вместо этого ИЗЛАГАЙ содержание напрямую
- Включай все конкретные данные: числа, названия инструментов, ссылки из статьи, параметры конфигурации
- Объём summary: от 2000 до 6000 символов. Не экономь на деталях
- Объём commentary: от 300 до 1000 символов
- Хештеги: от 3 до 7 штук, без символа #, маленькими буквами
- Если подходят существующие хештеги — используй их
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
    if not isinstance(result.get("commentary"), str):
        raise ValueError("Missing or invalid 'commentary'")
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
