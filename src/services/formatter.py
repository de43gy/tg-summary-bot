from __future__ import annotations

_MAX_LENGTH = 4096
_LINK_EMOJI = "\U0001f517"  # chain link
_ARTICLE_EMOJI = "\U0001f4ce"  # paperclip


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

    # Split: first message = header + as much summary as fits + "(1/N)"
    # subsequent = continuation + "(K/N)"
    # last = remainder + footer
    return _split_long_post(header, summary, footer)


def _split_long_post(header: str, summary: str, footer: str) -> list[str]:
    """Split a long post into multiple messages at paragraph boundaries."""
    paragraphs = summary.split("\n\n")
    messages: list[str] = []
    current_parts: list[str] = []
    current_len = len(header) + 2  # header + \n\n

    for para in paragraphs:
        # +2 for \n\n separator between paragraphs
        added_len = len(para) + (2 if current_parts else 0)

        if current_len + added_len > _MAX_LENGTH - 20:  # reserve for overflow
            if current_parts:
                if not messages:
                    # First message includes header
                    messages.append(header + "\n\n" + "\n\n".join(current_parts))
                else:
                    messages.append("\n\n".join(current_parts))
                current_parts = [para]
                current_len = len(para)
            else:
                # Single paragraph is too long — hard split by lines
                lines = para.split("\n")
                chunk: list[str] = []
                chunk_len = 0 if messages else len(header) + 2
                for line in lines:
                    if chunk_len + len(line) + 1 > _MAX_LENGTH - 20:
                        text = "\n".join(chunk)
                        if not messages:
                            messages.append(header + "\n\n" + text)
                        else:
                            messages.append(text)
                        chunk = [line]
                        chunk_len = len(line)
                    else:
                        chunk.append(line)
                        chunk_len += len(line) + 1
                current_parts = ["\n".join(chunk)] if chunk else []
                current_len = sum(len(p) for p in current_parts)
        else:
            current_parts.append(para)
            current_len += added_len

    # Last message: remaining text + footer
    remaining = "\n\n".join(current_parts) if current_parts else ""
    if not messages:
        # Everything fits after all — header + remaining + footer
        parts = [p for p in [header, remaining, footer] if p]
        messages.append("\n\n".join(parts))
    else:
        parts = [p for p in [remaining, footer] if p]
        if parts:
            last = "\n\n".join(parts)
            messages.append(last)

    return messages
