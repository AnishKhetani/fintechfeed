"""Engine tests use fake sources so aggregation logic is tested offline."""

from datetime import datetime, timezone

from fintechfeed.config import Config
from fintechfeed.engine import Engine
from fintechfeed.models import Item
from fintechfeed.sources.base import Source, SourceError


def _cfg(**overrides):
    base = Config(
        watchlist={"NVDA": ["Nvidia"], "TSLA": ["Tesla"]},
        sources={},
        sentiment={
            "source_weights": {"press": 1.0, "retail": 0.5},
            "min_mentions": 2,
            "bullish_at": 0.15,
            "bearish_at": -0.15,
        },
        llm={"enabled": False},
    )
    for k, v in overrides.items():
        setattr(base, k, v)
    return base


def _item(source, title, tickers=None):
    return Item(
        source=source,
        title=title,
        url=f"https://example.com/{abs(hash(title))}",
        published=datetime.now(timezone.utc),
        hint_tickers=tickers or [],
    )


class FakeSource(Source):
    def __init__(self, name, items):
        super().__init__({})
        self.name = name
        self._items = items

    def fetch(self, tickers):
        return self._items


class BrokenSource(Source):
    name = "broken"

    def fetch(self, tickers):
        raise SourceError("boom")


def test_min_mentions_filters_thin_tickers():
    src = FakeSource("press", [_item("press", "Nvidia rallies on strong guidance")])
    digest = Engine(_cfg(), sources=[src]).run()
    # Only one NVDA mention -> below min_mentions -> excluded.
    assert digest.tickers == []


def test_aggregates_and_labels():
    src = FakeSource(
        "press",
        [
            _item("press", "Nvidia beats earnings, guidance raised"),
            _item("press", "Nvidia surges to record high on strong demand"),
        ],
    )
    digest = Engine(_cfg(), sources=[src]).run()
    assert len(digest.tickers) == 1
    nvda = digest.tickers[0]
    assert nvda.ticker == "NVDA"
    assert nvda.mentions == 2
    assert nvda.label == "Bullish"
    assert nvda.score > 0


def test_source_weighting_moves_the_mean():
    # Press (weight 1.0) bullish, retail (weight 0.5) bearish -> net bullish.
    src = FakeSource(
        "press", [_item("press", "Tesla surges on record deliveries beat")]
    )
    retail = FakeSource(
        "retail", [_item("retail", "Tesla crash incoming, huge selloff")]
    )
    digest = Engine(_cfg(), sources=[src, retail]).run()
    tsla = next(t for t in digest.tickers if t.ticker == "TSLA")
    assert tsla.score > 0  # heavier press bullishness wins


def test_broken_source_is_recorded_not_fatal():
    good = FakeSource(
        "press",
        [
            _item("press", "Nvidia beats and raises guidance"),
            _item("press", "Nvidia rallies to record"),
        ],
    )
    engine = Engine(_cfg(), sources=[good, BrokenSource()])
    digest = engine.run()
    assert "broken" in engine.errors
    assert "press" in digest.sources_used
    assert len(digest.tickers) == 1


def test_deduplicates_by_url():
    dup = _item("press", "Nvidia beats and raises guidance")
    same = Item(source="press", title="different title", url=dup.url,
                published=dup.published, hint_tickers=["NVDA"])
    another = _item("press", "Nvidia surges to record")
    engine = Engine(_cfg(), sources=[FakeSource("press", [dup, same, another])])
    digest = engine.run()
    # `same` shares a URL with `dup` and is dropped -> 2 unique NVDA items.
    assert digest.tickers[0].mentions == 2
