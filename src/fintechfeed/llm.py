"""Optional LLM synthesis of the digest into a short analyst-style narrative.

Entirely opt-in: enabled only when config ``llm.enabled`` is true, the
``anthropic`` extra is installed, and ``ANTHROPIC_API_KEY`` is set. If any of
those is missing we return an empty narrative and the digest renders normally.
The point is to *summarise evidence FinTechFeed already gathered* — not to invent
facts — so the prompt is grounded strictly in the scored items.
"""

from __future__ import annotations

import os

from .models import Digest


def available(llm_config: dict) -> bool:
    if not llm_config.get("enabled"):
        return False
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return False
    try:
        import anthropic  # noqa: F401
    except ImportError:
        return False
    return True


def _build_prompt(digest: Digest) -> str:
    lines = ["Watchlist sentiment evidence gathered from public sources:\n"]
    for td in digest.tickers:
        lines.append(
            f"\n## {td.ticker} — {td.label} "
            f"(score {td.score:+.2f}, {td.mentions} mentions)"
        )
        for si in td.top_items[:3]:
            lines.append(f"- [{si.item.source}] {si.item.title} (sentiment {si.sentiment:+.2f})")
    lines.append(
        "\nWrite a concise 3-4 sentence market-desk brief. Only use the evidence "
        "above; do not invent prices, numbers, or events. Flag where retail "
        "(reddit) and press (yahoo_rss) disagree. Neutral, analytical tone."
    )
    return "\n".join(lines)


def synthesize(digest: Digest, llm_config: dict) -> str:
    """Return a narrative summary, or '' if synthesis is unavailable/failed."""
    if not available(llm_config) or not digest.tickers:
        return ""
    try:
        import anthropic

        client = anthropic.Anthropic()
        model = llm_config.get("model", "claude-haiku-4-5-20251001")
        msg = client.messages.create(
            model=model,
            max_tokens=400,
            messages=[{"role": "user", "content": _build_prompt(digest)}],
        )
        return "".join(block.text for block in msg.content if block.type == "text").strip()
    except Exception:
        # Synthesis is a nice-to-have; never let it break a digest run.
        return ""
