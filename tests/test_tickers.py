from fintechfeed.tickers import TickerResolver

WATCHLIST = {
    "NVDA": ["Nvidia"],
    "AAPL": ["Apple"],
    "BTC": ["Bitcoin", "BTC-USD"],
}


def test_cashtag_detection():
    r = TickerResolver(WATCHLIST)
    assert r.resolve("Loading up on $NVDA before earnings") == ["NVDA"]


def test_alias_matches_whole_word_only():
    r = TickerResolver(WATCHLIST)
    assert r.resolve("Apple unveils new chip") == ["AAPL"]
    # "applesauce" must NOT match AAPL.
    assert r.resolve("I love applesauce") == []


def test_bare_symbol_token():
    r = TickerResolver(WATCHLIST)
    assert "NVDA" in r.resolve("NVDA up 4% today")


def test_stopword_not_a_ticker():
    r = TickerResolver({"AI": ["C3.ai"]})
    # "AI" is a stopword, so the sentence noun should not resolve it...
    assert r.resolve("The AI boom continues") == []
    # ...but an explicit cashtag still does.
    assert r.resolve("$AI ripping today") == ["AI"]


def test_hints_respected_and_filtered():
    r = TickerResolver(WATCHLIST)
    assert r.resolve("some headline", hints=["NVDA"]) == ["NVDA"]
    # A hint outside the watchlist is ignored.
    assert r.resolve("some headline", hints=["ZZZZ"]) == []


def test_multiple_tickers_sorted():
    r = TickerResolver(WATCHLIST)
    assert r.resolve("Bitcoin and Nvidia both rally") == ["BTC", "NVDA"]
