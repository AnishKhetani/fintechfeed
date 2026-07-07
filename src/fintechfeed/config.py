"""Configuration loading with sane, key-free defaults.

FinTechFeed runs with zero setup: if no config file is found we fall back to a
built-in default watchlist and source set so ``fintechfeed digest`` works on a
fresh clone.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

DEFAULT_CONFIG: dict[str, Any] = {
    "watchlist": {
        "NVDA": ["Nvidia"],
        "AAPL": ["Apple"],
        "TSLA": ["Tesla"],
        "MSFT": ["Microsoft"],
        "BTC": ["Bitcoin", "BTC-USD"],
        "ETH": ["Ethereum", "ETH-USD"],
    },
    "sources": {
        "yahoo_rss": {"enabled": True},
        "reddit": {
            "enabled": True,
            "subreddits": ["stocks", "wallstreetbets", "investing", "cryptocurrency"],
            "listing": "hot",
            "limit": 40,
        },
        "hackernews": {"enabled": True, "limit": 20},
    },
    "sentiment": {
        "source_weights": {"yahoo_rss": 1.0, "reddit": 0.6, "hackernews": 0.8},
        "min_mentions": 2,
        "bullish_at": 0.15,
        "bearish_at": -0.15,
    },
    "llm": {"enabled": False, "model": "claude-haiku-4-5-20251001"},
}


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge ``override`` into a copy of ``base``."""
    out = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


@dataclass
class Config:
    watchlist: dict[str, list[str]]
    sources: dict[str, Any]
    sentiment: dict[str, Any]
    llm: dict[str, Any]
    path: Path | None = field(default=None)

    @classmethod
    def load(cls, path: str | Path | None = None) -> Config:
        """Load config from ``path``, else ``./config.yaml``, else defaults."""
        resolved: Path | None = None
        if path is not None:
            resolved = Path(path)
            if not resolved.exists():
                raise FileNotFoundError(f"Config not found: {resolved}")
        elif Path("config.yaml").exists():
            resolved = Path("config.yaml")

        data = DEFAULT_CONFIG
        if resolved is not None:
            loaded = yaml.safe_load(resolved.read_text(encoding="utf-8")) or {}
            data = _deep_merge(DEFAULT_CONFIG, loaded)

        return cls(
            watchlist={k: list(v or []) for k, v in data["watchlist"].items()},
            sources=data["sources"],
            sentiment=data["sentiment"],
            llm=data["llm"],
            path=resolved,
        )

    def enabled_sources(self) -> list[str]:
        return [name for name, cfg in self.sources.items() if cfg.get("enabled", False)]

    def source_weight(self, source: str) -> float:
        return float(self.sentiment.get("source_weights", {}).get(source, 1.0))
