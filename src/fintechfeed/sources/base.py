"""Base class for sources, with a shared resilient HTTP session.

The design borrows one idea from Agent-Reach: treat each platform as an
independent, swappable *channel* behind a uniform interface. A failure in one
source (rate limit, outage, schema change) degrades that channel only — the
digest still runs on whatever else responded.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from datetime import datetime, timezone

import requests

USER_AGENT = "fintechfeed/0.1 (+https://github.com/anishkhetani/fintechfeed)"
DEFAULT_TIMEOUT = 12
# Transient statuses worth one polite retry (rate limit / upstream hiccups).
_RETRY_STATUSES = {429, 502, 503, 504}
_MAX_RETRIES = 2


class SourceError(RuntimeError):
    """Raised when a source cannot fetch. Callers degrade gracefully."""


class Source(ABC):
    """A market-chatter channel."""

    #: config key / stable id used in weights and attribution
    name: str = "base"

    def __init__(self, config: dict | None = None):
        self.config = config or {}
        self._session = requests.Session()
        self._session.headers.update({"User-Agent": USER_AGENT})

    @abstractmethod
    def fetch(self, tickers: dict[str, list[str]]) -> list:
        """Fetch items for the given ``{ticker: [aliases]}`` watchlist.

        Returns a list of :class:`~fintechfeed.models.Item`. Implementations must
        raise :class:`SourceError` on failure rather than returning partial
        garbage, so the engine can record and skip the source.
        """

    # -- shared helpers -------------------------------------------------

    def _get(self, url: str, **kwargs) -> requests.Response:
        last_exc: Exception | None = None
        for attempt in range(_MAX_RETRIES + 1):
            try:
                resp = self._session.get(url, timeout=DEFAULT_TIMEOUT, **kwargs)
                if resp.status_code in _RETRY_STATUSES and attempt < _MAX_RETRIES:
                    self._backoff(resp, attempt)
                    continue
                resp.raise_for_status()
                return resp
            except requests.RequestException as exc:  # network, HTTP, timeout
                last_exc = exc
                if attempt < _MAX_RETRIES:
                    self._backoff(None, attempt)
                    continue
        raise SourceError(f"{self.name}: GET {url} failed: {last_exc}") from last_exc

    @staticmethod
    def _backoff(resp: requests.Response | None, attempt: int) -> None:
        """Sleep before a retry, honouring Retry-After when present."""
        delay = 0.75 * (2**attempt)  # 0.75s, 1.5s
        if resp is not None:
            retry_after = resp.headers.get("Retry-After")
            if retry_after and retry_after.isdigit():
                delay = min(float(retry_after), 5.0)
        time.sleep(delay)

    @staticmethod
    def _utc(ts: float | None) -> datetime:
        """Convert an epoch (or None) to a timezone-aware UTC datetime."""
        if ts is None:
            return datetime.now(timezone.utc)
        return datetime.fromtimestamp(ts, tz=timezone.utc)
