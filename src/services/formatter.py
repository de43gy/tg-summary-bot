from __future__ import annotations

_MAX_LENGTH = 4096
_LINK_EMOJI = "\U0001f517"  # chain link
_ARTICLE_EMOJI = "\U0001f4ce"  # paperclip
_COMMENT_EMOJI = "\U0001f4ac"  # speech bubble


def format_channel_post(
    title: str,
    summary: str,
    hashtags: list[str],
    original_url: str,
) -> list[str]:
    """Format a channel post, splitting into multiple messages if needed."""
    tags_line = " ".join(f"#{tag}" for tag in hashtags)
    link_line = f"{_LINK_EMOJI} {original_url}" if original_url else ""
    header = f"{_ARTICLE_EMOJI} {title}"

    footer_parts = [p for p in [tags_line, link_line] if p]
    footer = "\n\n".join(footer_parts)

    # Try to fit everything in one message
    full_text = "\n\n".join([p for p in [header, summary, footer] if p])
    if len(full_text) <= _MAX_LENGTH:
        return [full_text]

    return _split_long_post(header, summary, footer)


def format_commentary(commentary: str) -> str:
    """Format critical commentary for a reply message."""
    return f"{_COMMENT_EMOJI} Критический комментарий\n\n{commentary}"


def _split_long_post(header: str, summary: str, footer: str) -> list[str]:
    """Split a long post into multiple messages at paragraph boundaries.

    Guarantees every returned message is <= _MAX_LENGTH.
    """
    paragraphs = [p for p in summary.split("\n\n") if p.strip()]
    if not paragraphs:
        paragraphs = [summary]

    messages: list[str] = []
    current = header  # first message starts with header

    for para in paragraphs:
        candidate = current + "\n\n" + para
        if len(candidate) <= _MAX_LENGTH:
            current = candidate
        else:
            # Flush current message
            if current:
                messages.append(current)

            # Start new message with this paragraph
            if len(para) <= _MAX_LENGTH:
                current = para
            else:
                # Hard-split long paragraph by finding word/line boundaries
                chunks = _hard_split(para)
                messages.extend(chunks[:-1])
                current = chunks[-1] if chunks else ""

    # Append footer to last chunk, or as separate message
    if footer:
        candidate = current + "\n\n" + footer if current else footer
        if len(candidate) <= _MAX_LENGTH:
            current = candidate
        else:
            if current:
                messages.append(current)
            current = footer

    if current:
        messages.append(current)

    return messages if messages else [summary[:_MAX_LENGTH]]


def _hard_split(text: str, max_len: int = _MAX_LENGTH) -> list[str]:
    """Split text that exceeds max_len into chunks at line or word boundaries."""
    chunks: list[str] = []
    while len(text) > max_len:
        # Try to find a newline to split at
        split_at = text.rfind("\n", 0, max_len)
        if split_at < max_len // 2:
            # No good newline, try space
            split_at = text.rfind(" ", 0, max_len)
        if split_at < max_len // 2:
            # No good boundary, hard cut
            split_at = max_len
        chunks.append(text[:split_at])
        text = text[split_at:].lstrip()
    if text:
        chunks.append(text)
    return chunks
