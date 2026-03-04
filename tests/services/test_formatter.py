from src.services.formatter import _MAX_LENGTH, format_channel_post


class TestFormatChannelPost:
    def test_basic_format(self):
        result = format_channel_post(
            title="Заголовок статьи",
            summary="Подробный конспект статьи о Python и асинхронном программировании.",
            hashtags=["python", "asyncio"],
            original_url="https://example.com/article",
        )
        assert "\U0001f4ce Заголовок статьи" in result
        assert "Подробный конспект статьи" in result
        assert "#python #asyncio" in result
        assert "\U0001f517 https://example.com/article" in result

    def test_respects_max_length(self):
        long_summary = "A" * 5000
        result = format_channel_post(
            title="Заголовок",
            summary=long_summary,
            hashtags=["tag1", "tag2"],
            original_url="https://example.com/long",
        )
        assert len(result) <= _MAX_LENGTH

    def test_truncation_adds_ellipsis(self):
        long_summary = "Текст " * 1000
        result = format_channel_post(
            title="Заголовок",
            summary=long_summary,
            hashtags=["test"],
            original_url="https://example.com/page",
        )
        assert "..." in result

    def test_structure_four_parts(self):
        result = format_channel_post(
            title="Title",
            summary="Summary",
            hashtags=["tag"],
            original_url="https://example.com",
        )
        parts = result.split("\n\n")
        assert len(parts) == 4

    def test_multiple_hashtags(self):
        result = format_channel_post(
            title="T",
            summary="S",
            hashtags=["python", "web", "api", "rest"],
            original_url="https://example.com",
        )
        assert "#python #web #api #rest" in result

    def test_empty_hashtags(self):
        result = format_channel_post(
            title="T",
            summary="S",
            hashtags=[],
            original_url="https://example.com",
        )
        assert "\n\n" in result

    def test_short_summary_not_truncated(self):
        summary = "Краткий конспект."
        result = format_channel_post(
            title="Заголовок",
            summary=summary,
            hashtags=["test"],
            original_url="https://example.com",
        )
        assert summary in result
        assert "..." not in result

    def test_russian_content(self):
        result = format_channel_post(
            title="Обзор архитектуры микросервисов",
            summary="В статье рассматриваются основные паттерны проектирования микросервисов.",
            hashtags=["микросервисы", "архитектура"],
            original_url="https://habr.com/ru/articles/123",
        )
        assert "микросервисов" in result
        assert "#микросервисы #архитектура" in result

    def test_exact_max_length_boundary(self):
        title = "T"
        hashtags = ["t"]
        url = "https://x.com"
        header = f"\U0001f4ce {title}"
        tags_line = "#t"
        link_line = f"\U0001f517 {url}"
        skeleton_len = len(header) + len(tags_line) + len(link_line) + 6
        max_summary_len = _MAX_LENGTH - skeleton_len

        summary = "A" * max_summary_len
        result = format_channel_post(title, summary, hashtags, url)
        assert len(result) <= _MAX_LENGTH
        assert "..." not in result

    def test_summary_one_over_limit_gets_truncated(self):
        title = "T"
        hashtags = ["t"]
        url = "https://x.com"
        header = f"\U0001f4ce {title}"
        tags_line = "#t"
        link_line = f"\U0001f517 {url}"
        skeleton_len = len(header) + len(tags_line) + len(link_line) + 6
        max_summary_len = _MAX_LENGTH - skeleton_len

        summary = "A" * (max_summary_len + 10)
        result = format_channel_post(title, summary, hashtags, url)
        assert len(result) <= _MAX_LENGTH
        assert "..." in result
