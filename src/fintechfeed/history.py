"""Sentiment history — persist each run so the digest can show day-over-day
deltas and flag when a ticker's mood is turning.

History is a plain append-only JSONL file (one JSON object per run), kept local
and git-ignored. No database, no keys — in keeping with the rest of the tool.
Each run appends a compact record; the next run reads the most recent record
from a *previous calendar day* to compute a true day-over-day delta.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from .models import Digest


class HistoryStore:
    """Append-only per-run sentiment history backed by a JSONL file."""

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def append(self, digest: Digest) -> None:
        """Append one compact record capturing this run's per-ticker scores."""
        record = {
            "generated_at": digest.generated_at.isoformat(),
            "date": digest.generated_at.strftime("%Y-%m-%d"),
            "tickers": {
                td.ticker: {
                    "score": td.score,
                    "label": td.label,
                    "mentions": td.mentions,
                }
                for td in digest.tickers
            },
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")

    def records(self) -> list[dict]:
        """All stored run records, oldest first. Corrupt lines are skipped so a
        single bad write never breaks the history."""
        if not self.path.exists():
            return []
        out: list[dict] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return out

    def previous(self, before: datetime) -> dict[str, dict]:
        """Per-ticker snapshot from the most recent run on a calendar day
        *before* ``before`` — the day-over-day baseline. Empty if none exists."""
        cutoff = before.strftime("%Y-%m-%d")
        chosen: dict | None = None
        for rec in self.records():  # oldest first, so the last match is newest
            if str(rec.get("date", "")) < cutoff:
                chosen = rec
        return chosen.get("tickers", {}) if chosen else {}
