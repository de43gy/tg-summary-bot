from unittest.mock import AsyncMock, MagicMock, patch

from src.services.article_parser import extract_urls, fetch_and_parse, normalize_url


class TestExtractUrls:
    def test_single_url(self):
        text = "Check this out: https://example.com/article"
        assert extract_urls(text) == ["https://example.com/article"]

    def test_multiple_urls(self):
        text = "See https://a.com and http://b.com/page for details"
        result = extract_urls(text)
        assert len(result) == 2
        assert "https://a.com" in result
        assert "http://b.com/page" in result

    def test_no_urls(self):
        assert extract_urls("just plain text without links") == []

    def test_empty_string(self):
        assert extract_urls("") == []

    def test_url_with_query_params(self):
        text = "Link: https://example.com/page?foo=bar&baz=42"
        urls = extract_urls(text)
        assert len(urls) == 1
        assert "foo=bar" in urls[0]

    def test_url_with_fragment(self):
        text = "https://example.com/page#section"
        urls = extract_urls(text)
        assert len(urls) == 1

    def test_url_with_path(self):
        text = "https://blog.example.com/2024/01/my-article/"
        urls = extract_urls(text)
        assert len(urls) == 1
        assert "my-article" in urls[0]

    def test_url_among_markdown(self):
        text = "Read [this](https://example.com/post) article"
        urls = extract_urls(text)
        assert any("example.com/post" in u for u in urls)


class TestNormalizeUrl:
    def test_strip_utm_params(self):
        url = "https://example.com/article?utm_source=twitter&utm_medium=social&id=123"
        normalized = normalize_url(url)
        assert "utm_source" not in normalized
        assert "utm_medium" not in normalized
        assert "id=123" in normalized

    def test_strip_all_utm_variants(self):
        url = "https://example.com/?utm_source=a&utm_medium=b&utm_campaign=c&utm_term=d&utm_content=e"
        normalized = normalize_url(url)
        assert "utm_" not in normalized

    def test_strip_trailing_slash(self):
        url = "https://example.com/article/"
        normalized = normalize_url(url)
        assert not normalized.endswith("/article/")
        assert normalized.endswith("/article")

    def test_strip_fragment(self):
        url = "https://example.com/page#section"
        normalized = normalize_url(url)
        assert "#section" not in normalized

    def test_lowercase_scheme_and_host(self):
        url = "HTTPS://EXAMPLE.COM/Article"
        normalized = normalize_url(url)
        assert normalized.startswith("https://example.com")
        assert "/Article" in normalized

    def test_preserves_non_utm_query(self):
        url = "https://example.com/search?q=python&page=2"
        normalized = normalize_url(url)
        assert "q=python" in normalized
        assert "page=2" in normalized

    def test_empty_query_after_utm_strip(self):
        url = "https://example.com/page?utm_source=twitter"
        normalized = normalize_url(url)
        assert normalized == "https://example.com/page"

    def test_idempotent(self):
        url = "https://example.com/article?id=1"
        first = normalize_url(url)
        second = normalize_url(first)
        assert first == second


class TestFetchAndParse:
    async def test_fetch_and_parse_success(self):
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.text = "<html><body><p>Content</p></body></html>"
        mock_response.raise_for_status = MagicMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        with (
            patch("src.services.article_parser.get_http_client", return_value=mock_client),
            patch("src.services.article_parser.trafilatura.bare_extraction", return_value={
                "text": "Extracted article text about Python",
                "title": "Test Article",
            }),
        ):
            result = await fetch_and_parse("https://example.com/article")

        assert result is not None
        assert result.url == "https://example.com/article"
        assert result.text == "Extracted article text about Python"
        assert result.title == "Test Article"

    async def test_fetch_and_parse_http_error(self):
        import httpx

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=httpx.HTTPError("timeout"))

        with patch("src.services.article_parser.get_http_client", return_value=mock_client):
            result = await fetch_and_parse("https://example.com/broken")

        assert result is None

    async def test_fetch_and_parse_no_text_extracted(self):
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.text = "<html><body></body></html>"
        mock_response.raise_for_status = MagicMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        with (
            patch("src.services.article_parser.get_http_client", return_value=mock_client),
            patch("src.services.article_parser.trafilatura.bare_extraction", return_value=None),
        ):
            result = await fetch_and_parse("https://example.com/empty")

        assert result is None

    async def test_fetch_and_parse_empty_text_in_result(self):
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.text = "<html><body></body></html>"
        mock_response.raise_for_status = MagicMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        with (
            patch("src.services.article_parser.get_http_client", return_value=mock_client),
            patch("src.services.article_parser.trafilatura.bare_extraction", return_value={"text": ""}),
        ):
            result = await fetch_and_parse("https://example.com/empty")

        assert result is None

    async def test_fetch_and_parse_title_fallback_to_html(self):
        html = "<html><head><title>HTML Title</title></head><body><p>Content</p></body></html>"

        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.text = html
        mock_response.raise_for_status = MagicMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        with (
            patch("src.services.article_parser.get_http_client", return_value=mock_client),
            patch("src.services.article_parser.trafilatura.bare_extraction", return_value={
                "text": "Some article text",
                "title": "",
            }),
        ):
            result = await fetch_and_parse("https://example.com/fallback")

        assert result is not None
        assert result.title == "HTML Title"

    async def test_fetch_and_parse_default_title(self):
        html = "<html><body><p>Content without title</p></body></html>"

        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.text = html
        mock_response.raise_for_status = MagicMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        with (
            patch("src.services.article_parser.get_http_client", return_value=mock_client),
            patch("src.services.article_parser.trafilatura.bare_extraction", return_value={
                "text": "Content text",
                "title": "",
            }),
        ):
            result = await fetch_and_parse("https://example.com/notitle")

        assert result is not None
        assert result.title == "Без названия"
