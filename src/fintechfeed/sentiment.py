"""Finance-tuned sentiment scoring.

VADER is a solid, dependency-light baseline for social/news text, but its
lexicon is general-purpose: it has no opinion on "beat", "downgrade", or
"guidance cut". We extend it with a finance lexicon so market-moving language
is scored correctly. Scores are VADER's ``compound`` in [-1, 1].
"""

from __future__ import annotations

from functools import lru_cache

from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

# Domain terms and the valence VADER should assign them (its scale is roughly
# [-4, 4] per token). Signs and magnitudes reflect how the market reads them.
FINANCE_LEXICON: dict[str, float] = {
    # Bullish
    "beat": 2.2,
    "beats": 2.2,
    "upgrade": 2.6,
    "upgraded": 2.6,
    "outperform": 2.4,
    "bullish": 3.0,
    "rally": 2.3,
    "rallies": 2.3,
    "surge": 2.6,
    "surges": 2.6,
    "soar": 2.8,
    "soars": 2.8,
    "record": 1.6,
    "guidance raised": 3.0,
    "raises guidance": 3.0,
    "buyback": 1.8,
    "dividend": 1.2,
    "breakout": 2.0,
    "moon": 2.5,
    "long": 0.8,
    "accumulate": 1.5,
    # Bearish
    "miss": -2.2,
    "misses": -2.2,
    "downgrade": -2.8,
    "downgraded": -2.8,
    "underperform": -2.4,
    "bearish": -3.0,
    "selloff": -2.6,
    "sell-off": -2.6,
    "plunge": -3.0,
    "plunges": -3.0,
    "crash": -3.2,
    "tumble": -2.6,
    "tumbles": -2.6,
    "slump": -2.4,
    "guidance cut": -3.2,
    "cuts guidance": -3.2,
    "lawsuit": -1.8,
    "probe": -1.6,
    "investigation": -1.8,
    "bankruptcy": -3.5,
    "recall": -1.6,
    "layoffs": -1.4,
    "dilution": -1.8,
    "short": -0.8,
    "bagholder": -2.0,
    "rug": -3.0,
    "rugged": -3.0,
}


@lru_cache(maxsize=1)
def _analyzer() -> SentimentIntensityAnalyzer:
    analyzer = SentimentIntensityAnalyzer()
    # Multi-word phrases must be applied via booster handling; VADER's lexicon
    # is token-based, so single tokens go in the lexicon and phrases are
    # normalised in `score` before analysis.
    analyzer.lexicon.update({k: v for k, v in FINANCE_LEXICON.items() if " " not in k})
    return analyzer

# Phrases (multi-word) are collapsed to a sentinel token so VADER scores them.
_PHRASES = {k: k.replace(" ", "_") for k in FINANCE_LEXICON if " " in k}


def score(text: str) -> float:
    """Return the finance-tuned compound sentiment of ``text`` in [-1, 1]."""
    if not text or not text.strip():
        return 0.0
    analyzer = _analyzer()
    lowered = text
    for phrase, token in _PHRASES.items():
        if phrase in lowered.lower():
            # Register the sentinel token's valence once, then substitute.
            analyzer.lexicon.setdefault(token, FINANCE_LEXICON[phrase])
            lowered = _replace_ci(lowered, phrase, token)
    return analyzer.polarity_scores(lowered)["compound"]


def _replace_ci(text: str, old: str, new: str) -> str:
    """Case-insensitive replace of ``old`` with ``new``."""
    lower = text.lower()
    result = []
    i = 0
    step = len(old)
    while i < len(text):
        if lower[i : i + step] == old:
            result.append(new)
            i += step
        else:
            result.append(text[i])
            i += 1
    return "".join(result)


def label(compound: float, bullish_at: float, bearish_at: float) -> str:
    """Bucket a compound score into a Bullish / Neutral / Bearish label."""
    if compound >= bullish_at:
        return "Bullish"
    if compound <= bearish_at:
        return "Bearish"
    return "Neutral"
