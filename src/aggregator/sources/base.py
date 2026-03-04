from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import ClassVar


@dataclass
class ContentItem:
    source_name: str
    title: str
    url: str
    text: str
    language: str = "en"
    tags: list[str] = field(default_factory=list)
    fetched_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    meta: dict[str, object] = field(default_factory=dict)

    @property
    def dedup_key(self) -> str:
        return f"{self.source_name}:{self.url}"


SOURCE_REGISTRY: dict[str, type[ContentSource]] = {}


def register_source(name: str) -> Callable[[type[ContentSource]], type[ContentSource]]:
    def decorator(cls: type[ContentSource]) -> type[ContentSource]:
        SOURCE_REGISTRY[name] = cls
        return cls

    return decorator


class ContentSource(ABC):
    name: ClassVar[str] = ""

    @abstractmethod
    async def fetch(self) -> list[ContentItem]: ...

    @abstractmethod
    async def health_check(self) -> bool: ...

    async def close(self) -> None:  # noqa: B027
        pass
