import re
from dataclasses import dataclass
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import httpx
import trafilatura

_URL_RE = re.compile(r"https?://[^\s<>\"']+")

_UTM_PARAMS = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content"}


def extract_urls(text: str) -> list[str]:
    """Extract all HTTP/HTTPS URLs from text."""
    return _URL_RE.findall(text)


def normalize_url(url: str) -> str:
    """Normalize URL: strip UTM params, trailing slashes, fragments."""
    parsed = urlparse(url)

    # Filter out UTM params
    qs = parse_qs(parsed.query, keep_blank_values=False)
    filtered_qs = {k: v for k, v in qs.items() if k.lower() not in _UTM_PARAMS}
    clean_query = urlencode(filtered_qs, doseq=True)

    # Strip trailing slash from path
    path = parsed.path.rstrip("/")

    # Rebuild without fragment
    normalized = urlunparse(
        (
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            path,
            parsed.params,
            clean_query,
            "",  # no fragment
        )
    )
    return normalized


@dataclass
class ParsedArticle:
    url: str
    title: str
    text: str


_http_client: httpx.AsyncClient | None = None


def get_http_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None or _http_client.is_closed:
        _http_client = httpx.AsyncClient(
            follow_redirects=True,
            timeout=30.0,
            headers={"User-Agent": "Mozilla/5.0 (compatible; SummaryBot/1.0)"},
        )
    return _http_client


async def close_http_client() -> None:
    global _http_client
    if _http_client is not None:
        await _http_client.aclose()
        _http_client = None


async def fetch_and_parse(url: str) -> ParsedArticle | None:
    """Fetch URL and extract article text using trafilatura."""
    try:
        client = get_http_client()
        response = await client.get(url)
        response.raise_for_status()
        html = response.text
    except httpx.HTTPError:
        return None

    result = trafilatura.bare_extraction(html, include_comments=False, include_tables=True)
    if not result or not result.get("text"):
        return None

    text = result["text"]
    title = result.get("title", "")

    if not title:
        # Fallback: try to extract <title> from HTML
        title_match = re.search(r"<title[^>]*>([^<]+)</title>", html, re.IGNORECASE)
        if title_match:
            title = title_match.group(1).strip()

    return ParsedArticle(url=url, title=title or "Без названия", text=text)
