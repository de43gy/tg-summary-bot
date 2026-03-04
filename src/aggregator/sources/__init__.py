from __future__ import annotations

import importlib
import logging
from pathlib import Path

from src.aggregator.sources.base import SOURCE_REGISTRY, ContentItem, ContentSource, register_source

logger = logging.getLogger(__name__)

__all__ = ["SOURCE_REGISTRY", "ContentItem", "ContentSource", "load_sources", "register_source"]


def load_sources() -> None:
    package_dir = Path(__file__).parent
    for py_file in package_dir.glob("*.py"):
        if py_file.name.startswith("_") or py_file.name == "base.py":
            continue
        module_name = f"src.aggregator.sources.{py_file.stem}"
        try:
            importlib.import_module(module_name)
            logger.info("Loaded source module: %s", module_name)
        except Exception:
            logger.exception("Failed to load source module: %s", module_name)
