from fintechfeed import sentiment


def test_finance_terms_shift_sentiment():
    # Plain VADER is roughly neutral on these; the finance lexicon should not be.
    assert sentiment.score("Nvidia beats earnings, guidance raised") > 0.3
    assert sentiment.score("Tesla misses estimates, analyst downgrade") < -0.3


def test_phrase_scoring():
    assert sentiment.score("Company cuts guidance for the year") < -0.2
    assert sentiment.score("Board raises guidance sharply") > 0.2


def test_empty_is_neutral():
    assert sentiment.score("") == 0.0
    assert sentiment.score("   ") == 0.0


def test_label_thresholds():
    assert sentiment.label(0.5, 0.15, -0.15) == "Bullish"
    assert sentiment.label(-0.5, 0.15, -0.15) == "Bearish"
    assert sentiment.label(0.0, 0.15, -0.15) == "Neutral"
    # Boundary is inclusive.
    assert sentiment.label(0.15, 0.15, -0.15) == "Bullish"
