"""History store + day-over-day delta logic, all offline (temp files, fakes)."""

from datetime import datetime, timedelta, timezone

from fintechfeed.config import Config
from fintechfeed.engine import Engine
from fintechfeed.history import HistoryStore
from fintechfeed.models import Digest, Item, TickerDigest
from fintechfeed.sources.base import Source


class FakeSource(Source):
    def __init__(self, name, items):
        super().__init__({})
        self.name = name
        self._items = items

    def fetch(self, tickers):
        return self._items


def _cfg(**overrides):
    base = Config(
        watchlist={"NVDA": ["Nvidia"]},
        sources={},
        sentiment={
            "source_weights": {"press": 1.0},
            "min_mentions": 2,
            "bullish_at": 0.15,
            "bearish_at": -0.15,
            "turning_delta": 0.1,
        },
        llm={"enabled": False},
    )
    for k, v in overrides.items():
        setattr(base, k, v)
    return base


def _item(title):
    return Item(
        source="press",
        title=title,
        url=f"https://example.com/{abs(hash(title))}",
        published=datetime.now(timezone.utc),
        hint_tickers=["NVDA"],
    )


def _digest(when, score, label="Neutral"):
    return Digest(
        generated_at=when,
        tickers=[TickerDigest("NVDA", ["Nvidia"], 3, score, label)],
        total_items=3,
        sources_used=["press"],
    )


# -- store -------------------------------------------------------------


def test_append_and_records_roundtrip(tmp_path):
    store = HistoryStore(tmp_path / "h.jsonl")
    store.append(_digest(datetime(2026, 7, 7, 12, tzinfo=timezone.utc), 0.2, "Bullish"))
    recs = store.records()
    assert len(recs) == 1
    assert recs[0]["date"] == "2026-07-07"
    assert recs[0]["tickers"]["NVDA"]["score"] == 0.2
    assert recs[0]["tickers"]["NVDA"]["label"] == "Bullish"


def test_previous_picks_most_recent_prior_day(tmp_path):
    store = HistoryStore(tmp_path / "h.jsonl")
    store.append(_digest(datetime(2026, 7, 5, 12, tzinfo=timezone.utc), 0.0))
    store.append(_digest(datetime(2026, 7, 6, 12, tzinfo=timezone.utc), 0.1))  # baseline
    store.append(_digest(datetime(2026, 7, 7, 9, tzinfo=timezone.utc), 0.3))  # same day
    prev = store.previous(datetime(2026, 7, 7, 10, tzinfo=timezone.utc))
    assert prev["NVDA"]["score"] == 0.1


def test_previous_empty_when_only_same_day(tmp_path):
    store = HistoryStore(tmp_path / "h.jsonl")
    store.append(_digest(datetime(2026, 7, 7, 8, tzinfo=timezone.utc), 0.2, "Bullish"))
    assert store.previous(datetime(2026, 7, 7, 20, tzinfo=timezone.utc)) == {}


def test_records_skips_corrupt_lines(tmp_path):
    path = tmp_path / "h.jsonl"
    store = HistoryStore(path)
    store.append(_digest(datetime(2026, 7, 7, 8, tzinfo=timezone.utc), 0.2))
    with path.open("a", encoding="utf-8") as fh:
        fh.write("not json\n")
    assert len(store.records()) == 1


# -- delta / turning logic (deterministic via _apply_history) ----------


def _apply(store, score, label):
    """Seed `store` as the baseline, then annotate a today-digest at `score`."""
    engine = Engine(_cfg(), sources=[], history=store)
    digest = _digest(datetime.now(timezone.utc), score, label)
    engine._apply_history(digest)
    return digest.tickers[0]


def _seed_yesterday(store, score, label):
    store.append(_digest(datetime.now(timezone.utc) - timedelta(days=2), score, label))


def test_label_flip_is_always_turning(tmp_path):
    store = HistoryStore(tmp_path / "h.jsonl")
    _seed_yesterday(store, 0.0, "Neutral")
    nvda = _apply(store, 0.30, "Bullish")
    assert nvda.prev_label == "Neutral"
    assert nvda.delta == 0.30
    assert nvda.turning is True


def test_big_move_without_flip_is_turning(tmp_path):
    store = HistoryStore(tmp_path / "h.jsonl")
    _seed_yesterday(store, 0.20, "Bullish")
    nvda = _apply(store, 0.35, "Bullish")  # same label, +0.15 >= 0.1
    assert nvda.delta == 0.15
    assert nvda.turning is True


def test_small_move_within_threshold_is_not_turning(tmp_path):
    store = HistoryStore(tmp_path / "h.jsonl")
    _seed_yesterday(store, 0.55, "Bullish")
    nvda = _apply(store, 0.60, "Bullish")  # same label, +0.05 < 0.1
    assert nvda.delta == 0.05
    assert nvda.turning is False


# -- engine end-to-end -------------------------------------------------


def test_engine_records_and_annotates_a_run(tmp_path):
    store = HistoryStore(tmp_path / "h.jsonl")
    _seed_yesterday(store, -0.30, "Bearish")

    src = FakeSource(
        "press",
        [_item("Nvidia beats and raises guidance"), _item("Nvidia surges to record")],
    )
    digest = Engine(_cfg(), sources=[src], history=store).run()
    nvda = digest.tickers[0]

    assert nvda.prev_label == "Bearish"
    assert nvda.delta is not None and nvda.delta > 0
    assert nvda.turning is True  # flipped Bearish -> Bullish
    assert len(store.records()) == 2  # baseline + this run


def test_engine_no_prior_day_means_no_delta(tmp_path):
    store = HistoryStore(tmp_path / "h.jsonl")
    src = FakeSource(
        "press",
        [_item("Nvidia beats and raises guidance"), _item("Nvidia surges to record")],
    )
    digest = Engine(_cfg(), sources=[src], history=store).run()
    nvda = digest.tickers[0]

    assert nvda.delta is None
    assert nvda.turning is False
    assert len(store.records()) == 1
