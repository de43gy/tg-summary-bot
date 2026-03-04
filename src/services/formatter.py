_MAX_LENGTH = 4096
_LINK_EMOJI = "\U0001f517"  # chain link
_ARTICLE_EMOJI = "\U0001f4ce"  # paperclip


def format_channel_post(
    title: str,
    summary: str,
    hashtags: list[str],
    original_url: str,
) -> str:
    """Format a channel post respecting the 4096 char Telegram limit."""
    tags_line = " ".join(f"#{tag}" for tag in hashtags)
    link_line = f"{_LINK_EMOJI} {original_url}"
    header = f"{_ARTICLE_EMOJI} {title}"

    # Calculate space available for the summary
    # Structure: header \n\n summary \n\n tags \n\n link
    skeleton_len = len(header) + len(tags_line) + len(link_line) + 6  # 3x "\n\n"
    max_summary_len = _MAX_LENGTH - skeleton_len

    if len(summary) > max_summary_len:
        trim_to = max(0, max_summary_len - 3)
        summary = summary[:trim_to] + "..."

    parts = [header, summary, tags_line, link_line]
    return "\n\n".join(parts)
