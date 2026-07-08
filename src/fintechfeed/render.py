"""Rendering a :class:`Digest` to terminal, Markdown, or JSON."""

from __future__ import annotations

import json

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .models import Digest

_LABEL_STYLE = {"Bullish": "bold green", "Bearish": "bold red", "Neutral": "yellow"}
_LABEL_EMOJI = {"Bullish": "🟢", "Bearish": "🔴", "Neutral": "🟡"}


def _delta_arrow(delta: float) -> str:
    return "▲" if delta > 0 else "▼" if delta < 0 else "→"


def _turning_note(td) -> str:
    """A short human phrase for why a ticker is flagged as turning."""
    if td.prev_label and td.prev_label != td.label:
        return f"{td.ticker} ({td.prev_label}→{td.label})"
    return f"{td.ticker} ({td.delta:+.2f})"


def _has_deltas(digest) -> bool:
    return any(td.delta is not None for td in digest.tickers)


def _delta_term(td) -> str:
    """Rich-markup delta cell for the terminal table."""
    if td.delta is None:
        return "[dim]—[/dim]"
    color = "green" if td.delta > 0 else "red" if td.delta < 0 else "yellow"
    flag = " 🔄" if td.turning else ""
    return f"[{color}]{_delta_arrow(td.delta)} {td.delta:+.2f}[/{color}]{flag}"


def _delta_md(td) -> str:
    """Plain-text delta cell for the Markdown table."""
    if td.delta is None:
        return "—"
    flag = " 🔄" if td.turning else ""
    return f"{_delta_arrow(td.delta)} {td.delta:+.2f}{flag}"


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

    show_delta = _has_deltas(digest)
    table = Table(show_header=True, header_style="bold", expand=False)
    table.add_column("Ticker", style="bold")
    table.add_column("Signal")
    table.add_column("Score", justify="right")
    if show_delta:
        table.add_column("Δ 1d", justify="right")
    table.add_column("Mentions", justify="right")
    table.add_column("Sources")
    for td in digest.tickers:
        style = _LABEL_STYLE.get(td.label, "white")
        by_src = " ".join(f"{k}:{v}" for k, v in sorted(td.by_source.items()))
        row = [
            td.ticker,
            f"[{style}]{_LABEL_EMOJI.get(td.label,'')} {td.label}[/{style}]",
            f"{td.score:+.2f}",
        ]
        if show_delta:
            row.append(_delta_term(td))
        row += [str(td.mentions), by_src]
        table.add_row(*row)
    console.print(table)

    turning = [td for td in digest.tickers if td.turning]
    if turning:
        console.print(
            "[bold]🔄 Mood turning:[/bold] "
            + ", ".join(_turning_note(td) for td in turning)
        )

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

    show_delta = _has_deltas(digest)
    out += ["## Signals", ""]
    if show_delta:
        out += [
            "| Ticker | Signal | Score | Δ 1d | Mentions | Sources |",
            "| ------ | ------ | ----: | ---: | -------: | ------- |",
        ]
    else:
        out += [
            "| Ticker | Signal | Score | Mentions | Sources |",
            "| ------ | ------ | ----: | -------: | ------- |",
        ]
    for td in digest.tickers:
        by_src = ", ".join(f"{k}: {v}" for k, v in sorted(td.by_source.items()))
        delta = f" {_delta_md(td)} |" if show_delta else ""
        out.append(
            f"| **{td.ticker}** | {_LABEL_EMOJI.get(td.label,'')} {td.label} "
            f"| {td.score:+.2f} |{delta} {td.mentions} | {by_src} |"
        )
    out.append("")

    turning = [td for td in digest.tickers if td.turning]
    if turning:
        out += [
            f"> 🔄 **Mood turning:** {', '.join(_turning_note(td) for td in turning)}",
            "",
        ]

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
                "delta": td.delta,
                "prev_label": td.prev_label,
                "turning": td.turning,
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
