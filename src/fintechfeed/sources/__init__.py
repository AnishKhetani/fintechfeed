"""Source registry.

Each source is a small, self-contained connector that fetches market chatter
and normalises it into :class:`~fintechfeed.models.Item`. Sources register
themselves here so the CLI can enable/disable them purely from config.
"""

from __future__ import annotations

from .base import Source
from .edgar import EdgarSource
from .hackernews import HackerNewsSource
from .reddit import RedditSource
from .rss import YahooRssSource

# Maps the config key -> Source class.
REGISTRY: dict[str, type[Source]] = {
    "yahoo_rss": YahooRssSource,
    "edgar": EdgarSource,
    "reddit": RedditSource,
    "hackernews": HackerNewsSource,
}


def build_sources(enabled: list[str], config: dict) -> list[Source]:
    """Instantiate the enabled sources with their per-source config."""
    sources: list[Source] = []
    for name in enabled:
        cls = REGISTRY.get(name)
        if cls is None:
            continue
        sources.append(cls(config.get(name, {})))
    return sources


__all__ = ["Source", "REGISTRY", "build_sources"]
