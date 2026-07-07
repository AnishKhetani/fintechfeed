import json
from datetime import datetime, timezone

from fintechfeed import render
from fintechfeed.config import DEFAULT_CONFIG, Config
from fintechfeed.models import Digest, Item, ScoredItem, TickerDigest


def _sample_digest():
    item = Item(
        source="yahoo_rss",
        title="Nvidia beats and raises guidance",
        url="https://example.com/x",
        published=datetime(2026, 7, 7, tzinfo=timezone.utc),
        hint_tickers=["NVDA"],
    )
    td = TickerDigest(
        ticker="NVDA",
        aliases=["Nvidia"],
        mentions=3,
        score=0.42,
        label="Bullish",
        by_source={"yahoo_rss": 3},
        top_items=[ScoredItem(item=item, tickers=["NVDA"], sentiment=0.6, weight=1.0)],
    )
    return Digest(
        generated_at=datetime(2026, 7, 7, 12, 0, tzinfo=timezone.utc),
        tickers=[td],
        total_items=10,
        sources_used=["yahoo_rss"],
    )


def test_json_render_roundtrips():
    payload = json.loads(render.to_json(_sample_digest()))
    assert payload["tickers"][0]["ticker"] == "NVDA"
    assert payload["tickers"][0]["evidence"][0]["sentiment"] == 0.6
    assert payload["total_items"] == 10


def test_markdown_render_has_table_and_evidence():
    md = render.to_markdown(_sample_digest())
    assert "| **NVDA** |" in md
    assert "## Evidence" in md
    assert "https://example.com/x" in md


def test_config_defaults_when_no_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # no config.yaml here
    cfg = Config.load()
    assert cfg.path is None
    assert "NVDA" in cfg.watchlist
    assert cfg.enabled_sources()  # defaults enable sources


def test_config_deep_merge(tmp_path):
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text("sentiment:\n  min_mentions: 5\n", encoding="utf-8")
    cfg = Config.load(cfg_file)
    # Overridden key changes...
    assert cfg.sentiment["min_mentions"] == 5
    # ...but sibling defaults survive the merge.
    assert cfg.sentiment["bullish_at"] == DEFAULT_CONFIG["sentiment"]["bullish_at"]
