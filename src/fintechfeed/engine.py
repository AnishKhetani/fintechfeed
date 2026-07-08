"""The research pipeline: fetch -> score -> aggregate into a :class:`Digest`.

This is the heart of FinTechFeed. It fans out across enabled sources, resolves
each item to watchlist tickers, scores finance-tuned sentiment, then rolls the
evidence up into a per-ticker view with a weighted-mean score and a directional
label.
"""

from __future__ import annotations

from collections import defaultdict

from . import sentiment
from .config import Config
from .history import HistoryStore
from .models import Digest, Item, ScoredItem, TickerDigest
from .sources import Source, build_sources
from .tickers import TickerResolver


class Engine:
    def __init__(
        self,
        config: Config,
        sources: list[Source] | None = None,
        history: HistoryStore | None = None,
    ):
        self.config = config
        self.resolver = TickerResolver(config.watchlist)
        self.sources = (
            sources
            if sources is not None
            else build_sources(config.enabled_sources(), config.sources)
        )
        self.history = history
        self.errors: dict[str, str] = {}

    def _collect(self) -> list[Item]:
        """Fetch from every source, recording (not raising) per-source errors."""
        items: list[Item] = []
        for source in self.sources:
            try:
                items.extend(source.fetch(self.config.watchlist))
            except Exception as exc:  # a channel failing must not kill the run
                self.errors[source.name] = str(exc)
        return items

    def _score(self, items: list[Item]) -> list[ScoredItem]:
        scored: list[ScoredItem] = []
        seen_urls: set[str] = set()
        for item in items:
            if item.url and item.url in seen_urls:
                continue
            if item.url:
                seen_urls.add(item.url)
            tickers = self.resolver.resolve(item.text, item.hint_tickers)
            if not tickers:
                continue
            scored.append(
                ScoredItem(
                    item=item,
                    tickers=tickers,
                    sentiment=sentiment.score(item.text),
                    weight=self.config.source_weight(item.source),
                )
            )
        return scored

    def _aggregate(self, scored: list[ScoredItem]) -> list[TickerDigest]:
        sent_cfg = self.config.sentiment
        min_mentions = int(sent_cfg.get("min_mentions", 2))
        bull = float(sent_cfg.get("bullish_at", 0.15))
        bear = float(sent_cfg.get("bearish_at", -0.15))

        buckets: dict[str, list[ScoredItem]] = defaultdict(list)
        for si in scored:
            for ticker in si.tickers:
                if ticker in self.config.watchlist:
                    buckets[ticker].append(si)

        digests: list[TickerDigest] = []
        for ticker, group in buckets.items():
            if len(group) < min_mentions:
                continue
            weight_sum = sum(si.weight for si in group) or 1.0
            weighted = sum(si.sentiment * si.weight for si in group) / weight_sum

            by_source: dict[str, int] = defaultdict(int)
            for si in group:
                by_source[si.item.source] += 1

            # Most opinionated evidence first (largest |sentiment|), then weight.
            top = sorted(
                group, key=lambda s: (abs(s.sentiment), s.weight), reverse=True
            )[:5]

            digests.append(
                TickerDigest(
                    ticker=ticker,
                    aliases=self.config.watchlist.get(ticker, []),
                    mentions=len(group),
                    score=round(weighted, 4),
                    label=sentiment.label(weighted, bull, bear),
                    by_source=dict(by_source),
                    top_items=top,
                )
            )

        # Strongest conviction (by |score|), then most-discussed.
        digests.sort(key=lambda d: (abs(d.score), d.mentions), reverse=True)
        return digests

    def _apply_history(self, digest: Digest) -> None:
        """Annotate tickers with day-over-day deltas, then record this run."""
        prev = self.history.previous(digest.generated_at)
        turning_at = float(self.config.sentiment.get("turning_delta", 0.1))
        for td in digest.tickers:
            rec = prev.get(td.ticker)
            if rec is not None:
                td.prev_label = rec.get("label")
                td.delta = round(td.score - float(rec["score"]), 4)
                td.turning = td.prev_label != td.label or abs(td.delta) >= turning_at
        self.history.append(digest)

    def run(self) -> Digest:
        items = self._collect()
        scored = self._score(items)
        tickers = self._aggregate(scored)
        used = [s.name for s in self.sources if s.name not in self.errors]
        digest = Digest.now(
            tickers=tickers,
            total_items=len(items),
            sources_used=used,
        )
        if self.history is not None:
            self._apply_history(digest)
        return digest
