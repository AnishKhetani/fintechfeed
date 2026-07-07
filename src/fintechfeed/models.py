"""Core data structures shared across sources, sentiment, and the digest engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class Item:
    """A single piece of market chatter (a headline, post, or comment).

    Sources normalise their raw payloads into this shape so the sentiment and
    digest layers never need to know where an item came from.
    """

    source: str          # source id, e.g. "yahoo_rss", "reddit"
    title: str
    url: str
    published: datetime  # timezone-aware UTC
    summary: str = ""
    author: str = ""
    # Tickers the source already knows this item is about (e.g. a per-ticker
    # RSS feed). Name/cashtag extraction adds to this later.
    hint_tickers: list[str] = field(default_factory=list)

    @property
    def text(self) -> str:
        """Combined text used for ticker extraction and sentiment scoring."""
        return f"{self.title}. {self.summary}".strip()


@dataclass
class ScoredItem:
    """An :class:`Item` after sentiment scoring and ticker resolution."""

    item: Item
    tickers: list[str]
    sentiment: float       # VADER compound in [-1, 1]
    weight: float          # source trust weight applied during aggregation


@dataclass
class TickerDigest:
    """Aggregated sentiment and evidence for a single ticker."""

    ticker: str
    aliases: list[str]
    mentions: int
    score: float                       # weighted mean compound score
    label: str                         # Bullish | Neutral | Bearish
    by_source: dict[str, int] = field(default_factory=dict)
    top_items: list[ScoredItem] = field(default_factory=list)


@dataclass
class Digest:
    """A full research run: every ticker that cleared the mention threshold."""

    generated_at: datetime
    tickers: list[TickerDigest]
    total_items: int
    sources_used: list[str]
    narrative: str = ""                # optional LLM-written summary

    @classmethod
    def now(cls, **kwargs) -> Digest:
        return cls(generated_at=datetime.now(timezone.utc), **kwargs)
