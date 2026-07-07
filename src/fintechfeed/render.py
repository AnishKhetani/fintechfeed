"""Rendering a :class:`Digest` to terminal, Markdown, or JSON."""

from __future__ import annotations

import json

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .models import Digest

_LABEL_STYLE = {"Bullish": "bold green", "Bearish": "bold red", "Neutral": "yellow"}
_LABEL_EMOJI = {"Bullish": "🟢", "Bearish": "🔴", "Neutral": "🟡"}


def to_terminal(digest: Digest, console: Console | None = None) -> None:
    console = console or Console()
    ts = digest.generated_at.strftime("%Y-%m-%d %H:%M UTC")
    console.print(
        Panel.fit(
            f"[bold]FinTechFeed[/bold] market sentiment digest\n"
            f"[dim]{ts} · {digest.total_items} items · sources: "
            f"{', '.join(digest.sources_used) or 'none'}[/dim]",
            border_style="cyan",
        )
    )

    if not digest.tickers:
        console.print("[yellow]No tickers cleared the mention threshold.[/yellow]")
        return

    table = Table(show_header=True, header_style="bold", expand=False)
    table.add_column("Ticker", style="bold")
    table.add_column("Signal")
    table.add_column("Score", justify="right")
    table.add_column("Mentions", justify="right")
    table.add_column("Sources")
    for td in digest.tickers:
        style = _LABEL_STYLE.get(td.label, "white")
        by_src = " ".join(f"{k}:{v}" for k, v in sorted(td.by_source.items()))
        table.add_row(
            td.ticker,
            f"[{style}]{_LABEL_EMOJI.get(td.label,'')} {td.label}[/{style}]",
            f"{td.score:+.2f}",
            str(td.mentions),
            by_src,
        )
    console.print(table)

    if digest.narrative:
        console.print(Panel(digest.narrative, title="Desk brief", border_style="magenta"))

    top = digest.tickers[0]
    console.print(f"\n[bold]Top evidence — {top.ticker}[/bold]")
    for si in top.top_items[:3]:
        console.print(
            f"  [{_LABEL_STYLE.get('Bullish' if si.sentiment>0 else 'Bearish','white')}]"
            f"{si.sentiment:+.2f}[/] [dim]{si.item.source}[/dim] {si.item.title}"
        )


def to_markdown(digest: Digest) -> str:
    ts = digest.generated_at.strftime("%Y-%m-%d %H:%M UTC")
    out = [
        "# FinTechFeed — Market Sentiment Digest",
        "",
        f"*Generated {ts} · {digest.total_items} items scored · "
        f"sources: {', '.join(digest.sources_used) or 'none'}*",
        "",
    ]
    if digest.narrative:
        out += ["## Desk brief", "", digest.narrative, ""]

    out += [
        "## Signals",
        "",
        "| Ticker | Signal | Score | Mentions | Sources |",
        "| ------ | ------ | ----: | -------: | ------- |",
    ]
    for td in digest.tickers:
        by_src = ", ".join(f"{k}: {v}" for k, v in sorted(td.by_source.items()))
        out.append(
            f"| **{td.ticker}** | {_LABEL_EMOJI.get(td.label,'')} {td.label} "
            f"| {td.score:+.2f} | {td.mentions} | {by_src} |"
        )
    out.append("")

    out += ["## Evidence", ""]
    for td in digest.tickers:
        out.append(f"### {td.ticker} — {td.label} ({td.score:+.2f})")
        for si in td.top_items:
            out.append(
                f"- `{si.sentiment:+.2f}` [{si.item.title}]({si.item.url}) "
                f"— *{si.item.source}*"
            )
        out.append("")
    return "\n".join(out)


def to_json(digest: Digest) -> str:
    payload = {
        "generated_at": digest.generated_at.isoformat(),
        "total_items": digest.total_items,
        "sources_used": digest.sources_used,
        "narrative": digest.narrative,
        "tickers": [
            {
                "ticker": td.ticker,
                "label": td.label,
                "score": td.score,
                "mentions": td.mentions,
                "by_source": td.by_source,
                "evidence": [
                    {
                        "source": si.item.source,
                        "title": si.item.title,
                        "url": si.item.url,
                        "sentiment": round(si.sentiment, 4),
                        "published": si.item.published.isoformat(),
                    }
                    for si in td.top_items
                ],
            }
            for td in digest.tickers
        ],
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)
