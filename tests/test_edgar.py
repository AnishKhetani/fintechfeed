"""EDGAR source tests. The HTTP layer is stubbed so parsing/normalisation of
SEC's ticker map and submissions JSON is tested offline."""

import pytest

from fintechfeed.sources.base import SourceError
from fintechfeed.sources.edgar import EdgarSource

TICKER_MAP = {
    "0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
    "1": {"cik_str": 1045810, "ticker": "NVDA", "title": "NVIDIA CORP"},
}

# Two 8-Ks plus a 10-Q that must be filtered out, newest first.
SUBMISSIONS_AAPL = {
    "name": "Apple Inc.",
    "filings": {
        "recent": {
            "form": ["8-K", "10-Q", "8-K"],
            "filingDate": ["2026-07-01", "2026-06-15", "2026-06-01"],
            "items": ["2.02,9.01", "", "2.06"],
            "accessionNumber": [
                "0000320193-26-000070",
                "0000320193-26-000065",
                "0000320193-26-000060",
            ],
            "primaryDocument": ["aapl-20260701.htm", "aapl-10q.htm", "aapl-20260601.htm"],
        }
    },
}


class _FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


def _stub(src, *, map_payload=TICKER_MAP, subs=None, fail_map=False):
    subs = subs if subs is not None else {320193: SUBMISSIONS_AAPL}

    def fake_get(url, **kwargs):
        if url.endswith("company_tickers.json"):
            if fail_map:
                raise SourceError("edgar: map down")
            return _FakeResp(map_payload)
        for cik, payload in subs.items():
            if f"CIK{cik:010d}" in url:
                return _FakeResp(payload)
        raise SourceError(f"unexpected url: {url}")

    src._get = fake_get
    return src


def test_pulls_and_normalises_8k_filings():
    src = _stub(EdgarSource({"lookback_days": 36_500, "limit": 10}))
    items = src.fetch({"AAPL": ["Apple"]})

    # The 10-Q is filtered out; both 8-Ks survive.
    assert len(items) == 2
    first = items[0]
    assert first.source == "edgar"
    assert first.hint_tickers == ["AAPL"]
    assert "Apple Inc. (AAPL) 8-K" in first.title
    assert "Results of Operations and Financial Condition" in first.title
    assert first.url == (
        "https://www.sec.gov/Archives/edgar/data/320193/"
        "000032019326000070/aapl-20260701.htm"
    )
    # The bearish "Material Impairments" 8-K maps its item code to readable text.
    assert "Material Impairments" in items[1].summary


def test_lookback_window_excludes_old_filings():
    src = _stub(EdgarSource({"lookback_days": 1, "limit": 10}))
    # Every fixture filing predates a 1-day window.
    assert src.fetch({"AAPL": ["Apple"]}) == []


def test_limit_caps_filings_per_ticker():
    src = _stub(EdgarSource({"lookback_days": 36_500, "limit": 1}))
    assert len(src.fetch({"AAPL": ["Apple"]})) == 1


def test_ticker_without_cik_is_skipped():
    src = _stub(EdgarSource({"lookback_days": 36_500}))
    # BTC has no US filer -> no CIK -> silently skipped, no error.
    assert src.fetch({"BTC": ["Bitcoin"]}) == []


def test_unreachable_ticker_map_raises():
    src = _stub(EdgarSource({}), fail_map=True)
    with pytest.raises(SourceError):
        src.fetch({"AAPL": ["Apple"]})


def test_per_company_failure_is_not_fatal():
    # NVDA's submissions 404; AAPL's succeed -> AAPL items still returned.
    src = _stub(
        EdgarSource({"lookback_days": 36_500}),
        subs={320193: SUBMISSIONS_AAPL},  # 1045810 (NVDA) missing -> SourceError
    )
    items = src.fetch({"AAPL": ["Apple"], "NVDA": ["Nvidia"]})
    assert {i.hint_tickers[0] for i in items} == {"AAPL"}
