from src.services.formatter import _MAX_LENGTH, format_channel_post


class TestFormatChannelPost:
    def test_basic_format(self):
        parts = format_channel_post(
            title="Заголовок статьи",
            summary="Подробный конспект статьи о Python и асинхронном программировании.",
            hashtags=["python", "asyncio"],
            original_url="https://example.com/article",
        )
        assert len(parts) >= 1
        full = "\n\n".join(parts)
        assert "\U0001f4ce Заголовок статьи" in full
        assert "Подробный конспект статьи" in full
        assert "#python #asyncio" in full
        assert "\U0001f517 https://example.com/article" in full

    def test_short_post_single_message(self):
        parts = format_channel_post(
            title="Title",
            summary="Short summary",
            hashtags=["tag"],
            original_url="https://example.com",
        )
        assert len(parts) == 1

    def test_each_part_respects_max_length(self):
        long_summary = ("Параграф текста. " * 50 + "\n\n") * 20
        parts = format_channel_post(
            title="Заголовок",
            summary=long_summary,
            hashtags=["tag1", "tag2"],
            original_url="https://example.com/long",
        )
        for part in parts:
            assert len(part) <= _MAX_LENGTH

    def test_long_post_splits_into_multiple(self):
        long_summary = ("Параграф текста. " * 50 + "\n\n") * 20
        parts = format_channel_post(
            title="Заголовок",
            summary=long_summary,
            hashtags=["tag1"],
            original_url="https://example.com/long",
        )
        assert len(parts) > 1

    def test_structure_four_parts_short_post(self):
        parts = format_channel_post(
            title="Title",
            summary="Summary",
            hashtags=["tag"],
            original_url="https://example.com",
        )
        assert len(parts) == 1
        sections = parts[0].split("\n\n")
        assert len(sections) == 4

    def test_multiple_hashtags(self):
        parts = format_channel_post(
            title="T",
            summary="S",
            hashtags=["python", "web", "api", "rest"],
            original_url="https://example.com",
        )
        full = "\n\n".join(parts)
        assert "#python #web #api #rest" in full

    def test_empty_hashtags(self):
        parts = format_channel_post(
            title="T",
            summary="S",
            hashtags=[],
            original_url="https://example.com",
        )
        assert len(parts) >= 1

    def test_short_summary_not_split(self):
        summary = "Краткий конспект."
        parts = format_channel_post(
            title="Заголовок",
            summary=summary,
            hashtags=["test"],
            original_url="https://example.com",
        )
        assert len(parts) == 1
        assert summary in parts[0]

    def test_russian_content(self):
        parts = format_channel_post(
            title="Обзор архитектуры микросервисов",
            summary="В статье рассматриваются основные паттерны проектирования микросервисов.",
            hashtags=["микросервисы", "архитектура"],
            original_url="https://habr.com/ru/articles/123",
        )
        full = "\n\n".join(parts)
        assert "микросервисов" in full
        assert "#микросервисы #архитектура" in full

    def test_footer_in_last_message(self):
        long_summary = ("Параграф текста. " * 50 + "\n\n") * 20
        parts = format_channel_post(
            title="Заголовок",
            summary=long_summary,
            hashtags=["tag1"],
            original_url="https://example.com/page",
        )
        last = parts[-1]
        assert "#tag1" in last
        assert "https://example.com/page" in last

    def test_header_in_first_message(self):
        long_summary = ("Параграф текста. " * 50 + "\n\n") * 20
        parts = format_channel_post(
            title="Заголовок",
            summary=long_summary,
            hashtags=["tag1"],
            original_url="https://example.com/page",
        )
        assert "\U0001f4ce Заголовок" in parts[0]
