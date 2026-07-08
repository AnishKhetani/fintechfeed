"""SEC EDGAR 8-K filings as a primary-source sentiment channel.

Public companies disclose material events on Form 8-K. EDGAR exposes every
filing for free (no API key), keyed by a company's CIK:

    https://www.sec.gov/files/company_tickers.json       (ticker -> CIK)
    https://data.sec.gov/submissions/CIK##########.json  (a company's filings)

We resolve each watchlist ticker to its CIK, pull its recent 8-Ks, and turn each
filing's *item codes* into readable text — "Results of Operations", "Material
Impairments", "Bankruptcy or Receivership" — which the finance-tuned sentiment
model then scores. Filings are factual and authoritative, so this is the
highest-trust channel: neutral by default, but decisive when one signals an
impairment, delisting, or bankruptcy.

Only US-listed filers have a CIK, so tickers without one (e.g. BTC) are skipped.
SEC asks API clients to send a descriptive User-Agent, which the shared HTTP
session already does.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

from ..models import Item
from .base import Source, SourceError

TICKER_MAP_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"

# SEC's fair-access policy requires a User-Agent that identifies the requester
# with a contact, in a plain "name email" form (URLs/parentheses get blocked).
# The default keeps the zero-config promise; set `user_agent` in config or the
# SEC_EDGAR_USER_AGENT env var to your own contact, which SEC etiquette prefers.
DEFAULT_USER_AGENT = "FinTechFeed research tool admin@example.com"

# The 8-K item taxonomy. The wording is chosen so the market's read of each
# event carries through the finance sentiment lexicon (e.g. "bankruptcy",
# "impairment", "delisting" score bearish; the rest are factual and neutral).
ITEM_DESCRIPTIONS: dict[str, str] = {
    "1.01": "Entry into a Material Definitive Agreement",
    "1.02": "Termination of a Material Definitive Agreement",
    "1.03": "Bankruptcy or Receivership",
    "2.01": "Completion of Acquisition or Disposition of Assets",
    "2.02": "Results of Operations and Financial Condition",
    "2.03": "Creation of a Direct Financial Obligation",
    "2.04": "Triggering Events Accelerating a Financial Obligation",
    "2.05": "Costs Associated with Exit or Disposal Activities",
    "2.06": "Material Impairments",
    "3.01": "Notice of Delisting or Failure to Satisfy a Listing Rule",
    "3.02": "Unregistered Sales of Equity Securities",
    "3.03": "Material Modification to Rights of Security Holders",
    "4.01": "Changes in Registrant's Certifying Accountant",
    "4.02": "Non-Reliance on Previously Issued Financial Statements",
    "5.01": "Changes in Control of Registrant",
    "5.02": "Departure or Appointment of Directors or Officers",
    "5.03": "Amendments to Articles of Incorporation or Bylaws",
    "5.07": "Submission of Matters to a Vote of Security Holders",
    "7.01": "Regulation FD Disclosure",
    "8.01": "Other Events",
    "9.01": "Financial Statements and Exhibits",
}


class EdgarSource(Source):
    """SEC EDGAR 8-K material-event filings (primary source, no API key)."""

    name = "edgar"

    def __init__(self, config: dict | None = None):
        super().__init__(config)
        # SEC blocks the shared library User-Agent; use a compliant contact UA
        # on this source's own session only.
        ua = (
            self.config.get("user_agent")
            or os.environ.get("SEC_EDGAR_USER_AGENT")
            or DEFAULT_USER_AGENT
        )
        self._session.headers["User-Agent"] = ua

    def fetch(self, tickers: dict[str, list[str]]) -> list[Item]:
        forms = {f.upper() for f in self.config.get("forms", ["8-K"])}
        limit = int(self.config.get("limit", 10))
        lookback_days = int(self.config.get("lookback_days", 30))
        cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)

        # A failed ticker map means EDGAR itself is unreachable -> the channel
        # is down. Per-company failures below are skipped, not fatal.
        cik_map = self._ticker_to_cik()

        items: list[Item] = []
        for ticker in tickers:
            cik = cik_map.get(ticker.upper())
            if cik is None:  # no US filer for this symbol (e.g. a crypto pair)
                continue
            try:
                data = self._get(SUBMISSIONS_URL.format(cik=cik)).json()
                recent = data["filings"]["recent"]
            except (SourceError, ValueError, KeyError):
                continue
            name = data.get("name") or ticker
            items.extend(
                self._filings_for(ticker, name, cik, recent, forms, limit, cutoff)
            )
        return items

    # -- helpers --------------------------------------------------------

    def _ticker_to_cik(self) -> dict[str, int]:
        """Fetch SEC's ticker->CIK directory once and index it by symbol."""
        try:
            data = self._get(TICKER_MAP_URL).json()
        except (SourceError, ValueError) as exc:
            raise SourceError(f"edgar: ticker map unavailable: {exc}") from exc
        out: dict[str, int] = {}
        for row in data.values():
            symbol = str(row.get("ticker", "")).upper()
            cik = row.get("cik_str")
            if symbol and cik is not None:
                out[symbol] = int(cik)
        return out

    def _filings_for(
        self, ticker, name, cik, recent, forms, limit, cutoff
    ) -> list[Item]:
        # `recent` holds parallel arrays, newest filing first.
        col_form = recent.get("form", [])
        col_date = recent.get("filingDate", [])
        col_items = recent.get("items", [])
        col_accession = recent.get("accessionNumber", [])
        col_doc = recent.get("primaryDocument", [])

        out: list[Item] = []
        for i, form in enumerate(col_form):
            if len(out) >= limit:
                break
            if form.upper() not in forms:
                continue
            published = self._filing_date(col_date[i] if i < len(col_date) else "")
            if published < cutoff:
                continue
            codes = col_items[i] if i < len(col_items) else ""
            desc = self._describe(codes)
            out.append(
                Item(
                    source=self.name,
                    title=f"{name} ({ticker}) {form}: {desc}" if desc
                    else f"{name} ({ticker}) {form} filing",
                    url=self._filing_url(
                        cik,
                        col_accession[i] if i < len(col_accession) else "",
                        col_doc[i] if i < len(col_doc) else "",
                    ),
                    published=published,
                    summary=desc,
                    hint_tickers=[ticker],
                )
            )
        return out

    @staticmethod
    def _describe(codes: str) -> str:
        """Turn an ``"2.02,9.01"`` item string into readable event names."""
        parts = [
            ITEM_DESCRIPTIONS.get(c.strip(), f"Item {c.strip()}")
            for c in codes.split(",")
            if c.strip()
        ]
        return "; ".join(parts)

    @staticmethod
    def _filing_url(cik: int, accession: str, primary_doc: str) -> str:
        acc_nodash = accession.replace("-", "")
        base = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc_nodash}"
        if primary_doc:
            return f"{base}/{primary_doc}"
        if accession:
            return f"{base}/{accession}-index.htm"
        return f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik:010d}"

    def _filing_date(self, value: str) -> datetime:
        try:
            return datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            return self._utc(None)
