"""Reddit via the public RSS feeds.

Reddit's ``.json`` listings now 403 from most non-authenticated / datacenter
clients, but the per-subreddit RSS feeds remain openly available:

    https://www.reddit.com/r/stocks/.rss          (hot)
    https://www.reddit.com/r/stocks/new/.rss      (new)
    https://www.reddit.com/r/stocks/top/.rss      (top)

We pull the configured subreddits and let the ticker resolver decide which
posts are on-watchlist, since retail threads rarely tag symbols cleanly.
"""

from __future__ import annotations

import re
import time
from calendar import timegm

import feedparser

from ..models import Item
from .base import Source, SourceError

FEED_URL = "https://www.reddit.com/r/{sub}/{path}.rss?limit={limit}"


class RedditSource(Source):
    """Retail sentiment from configurable subreddit RSS feeds."""

    name = "reddit"

    def fetch(self, tickers: dict[str, list[str]]) -> list[Item]:
        subs = self.config.get("subreddits", ["stocks", "wallstreetbets"])
        listing = self.config.get("listing", "hot")
        limit = int(self.config.get("limit", 40))
        # "hot" is the bare feed; other listings take a path segment.
        path = "" if listing == "hot" else f"{listing}/"

        items: list[Item] = []
        failures = 0
        for sub in subs:
            url = FEED_URL.format(sub=sub, path=path, limit=limit)
            try:
                resp = self._get(url)
            except SourceError:
                failures += 1
                continue
            feed = feedparser.parse(resp.content)
            if feed.bozo and not feed.entries:
                failures += 1
                continue
            for entry in feed.entries:
                items.append(
                    Item(
                        source=self.name,
                        title=entry.get("title", "").strip(),
                        url=entry.get("link", ""),
                        published=self._entry_time(entry),
                        summary=_strip_html(entry.get("summary", ""))[:600],
                        author=entry.get("author", "").lstrip("/u"),
                    )
                )
        if failures and failures == len(subs):
            raise SourceError("reddit: all subreddit feeds failed")
        return items

    def _entry_time(self, entry) -> object:
        parsed = entry.get("published_parsed") or entry.get("updated_parsed")
        if parsed:
            return self._utc(timegm(parsed))
        return self._utc(time.time())


def _strip_html(html: str) -> str:
    text = re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", text).strip()
