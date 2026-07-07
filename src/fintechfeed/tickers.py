"""Resolve which watchlist tickers a piece of text is about.

Two complementary signals:

* **Cashtags** — ``$NVDA`` style mentions, the convention on FinTwit/Reddit.
* **Aliases** — company/asset names ("Nvidia", "Bitcoin") matched as whole
  words, so "Apple" hits AAPL but "applesauce" does not.

Bare ticker symbols without a ``$`` (e.g. the word "AAPL") are also matched,
but only when they are 2+ chars and appear as an isolated uppercase token, to
avoid false positives on common English words.
"""

from __future__ import annotations

import re

# Uppercase tokens that are valid English words / abbreviations and would
# otherwise be mistaken for tickers.
_TICKER_STOPWORDS = {
    "A", "I", "AI", "CEO", "CFO", "IPO", "USA", "US", "UK", "EU", "GDP",
    "ETF", "SEC", "FED", "API", "CPI", "PPI", "YOY", "EPS", "ATH", "DD",
}


def _word_pattern(word: str) -> re.Pattern[str]:
    return re.compile(rf"\b{re.escape(word)}\b", re.IGNORECASE)


class TickerResolver:
    """Maps free text to the subset of a watchlist it references."""

    def __init__(self, watchlist: dict[str, list[str]]):
        self.watchlist = watchlist
        self._alias_patterns: dict[str, list[re.Pattern[str]]] = {}
        for ticker, aliases in watchlist.items():
            pats = [_word_pattern(a) for a in aliases if a]
            self._alias_patterns[ticker] = pats

    def resolve(self, text: str, hints: list[str] | None = None) -> list[str]:
        """Return watchlist tickers referenced by ``text`` (plus valid hints)."""
        found: set[str] = set()

        for hint in hints or []:
            if hint in self.watchlist:
                found.add(hint)

        cashtags = {m.upper() for m in re.findall(r"\$([A-Za-z]{1,6})\b", text)}

        upper_tokens = {
            t
            for t in re.findall(r"\b[A-Z]{2,6}\b", text)
            if t not in _TICKER_STOPWORDS
        }

        for ticker, patterns in self._alias_patterns.items():
            if ticker in found:
                continue
            if ticker in cashtags or ticker in upper_tokens:
                found.add(ticker)
                continue
            if any(p.search(text) for p in patterns):
                found.add(ticker)

        return sorted(found)
