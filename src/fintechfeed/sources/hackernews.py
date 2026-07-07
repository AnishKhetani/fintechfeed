"""Hacker News via the free Algolia search API.

We query per ticker (by symbol and by primary alias) so stories are pre-tagged.
HN skews toward tech/crypto, which complements the finance-press RSS feed.

    https://hn.algolia.com/api/v1/search?query=Nvidia&tags=story
"""

from __future__ import annotations

from ..models import Item
from .base import Source, SourceError

SEARCH_URL = "https://hn.algolia.com/api/v1/search"


class HackerNewsSource(Source):
    """Tech and crypto stories via the free HN Algolia search API."""

    name = "hackernews"

    def fetch(self, tickers: dict[str, list[str]]) -> list[Item]:
        limit = int(self.config.get("limit", 20))
        items: list[Item] = []
        seen: set[str] = set()
        failures = 0
        queries = 0

        for ticker, aliases in tickers.items():
            # Prefer the company name over the raw symbol to cut false hits
            # (e.g. "ETH" the token vs "Ethereum").
            query = aliases[0] if aliases else ticker
            queries += 1
            try:
                resp = self._get(
                    SEARCH_URL,
                    params={"query": query, "tags": "story", "hitsPerPage": limit},
                )
                hits = resp.json().get("hits", [])
            except (SourceError, ValueError):
                failures += 1
                continue
            for hit in hits:
                object_id = hit.get("objectID", "")
                if object_id in seen:
                    continue
                seen.add(object_id)
                title = (hit.get("title") or hit.get("story_title") or "").strip()
                if not title:
                    continue
                items.append(
                    Item(
                        source=self.name,
                        title=title,
                        url=hit.get("url")
                        or f"https://news.ycombinator.com/item?id={object_id}",
                        published=self._utc(hit.get("created_at_i")),
                        author=hit.get("author", ""),
                        hint_tickers=[ticker],
                    )
                )
        if failures and failures == queries:
            raise SourceError("hackernews: all queries failed")
        return items
