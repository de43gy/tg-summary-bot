from dataclasses import dataclass
from datetime import datetime


@dataclass
class Article:
    id: int
    url: str
    url_normalized: str
    title: str | None
    summary: str | None
    status: str
    error_message: str | None
    channel_message_id: int | None
    chat_id: int | None
    retry_count: int
    created_at: datetime
    updated_at: datetime


@dataclass
class Hashtag:
    id: int
    name: str
    created_at: datetime
