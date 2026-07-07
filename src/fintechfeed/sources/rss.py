"""Yahoo Finance per-ticker news RSS.

Yahoo exposes a free, key-less headline feed per symbol:

    https://feeds.finance.yahoo.com/rss/2.0/headline?s=NVDA&region=US&lang=en-US

Because the feed is queried per symbol, every item arrives already tagged with
the ticker it belongs to — the highest-signal source in the set.
"""

from __future__ import annotations

import time
from calendar import timegm

import feedparser

from ..models import Item
from .base import Source, SourceError

FEED_URL = "https://feeds.finance.yahoo.com/rss/2.0/headline?s={symbol}&region=US&lang=en-US"


class YahooRssSource(Source):
    """Per-ticker financial-press headlines from Yahoo Finance RSS."""

    name = "yahoo_rss"

    def fetch(self, tickers: dict[str, list[str]]) -> list[Item]:
        items: list[Item] = []
        failures = 0
        for ticker in tickers:
            try:
                resp = self._get(FEED_URL.format(symbol=ticker))
            except SourceError:
                failures += 1
                continue
            feed = feedparser.parse(resp.content)
            for entry in feed.entries:
                items.append(
                    Item(
                        source=self.name,
                        title=entry.get("title", "").strip(),
                        url=entry.get("link", ""),
                        published=self._entry_time(entry),
                        summary=_clean(entry.get("summary", "")),
                        hint_tickers=[ticker],
                    )
                )
        # If every symbol failed, the source is down — signal it.
        if failures and failures == len(tickers):
            raise SourceError("yahoo_rss: all symbol feeds failed")
        return items

    def _entry_time(self, entry) -> object:
        parsed = entry.get("published_parsed") or entry.get("updated_parsed")
        if parsed:
            return self._utc(timegm(parsed))
        return self._utc(time.time())


def _clean(html: str) -> str:
    """Strip the light HTML Yahoo puts in summaries."""
    import re

    text = re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", text).strip()
