"""Command-line interface: ``fintechfeed digest | sources | doctor``."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from rich.console import Console
from rich.table import Table

from . import __version__, llm, render
from .config import Config
from .engine import Engine
from .history import HistoryStore
from .sources import REGISTRY, build_sources


def _cmd_digest(args: argparse.Namespace) -> int:
    console = Console()
    config = Config.load(args.config)

    if args.tickers:
        wanted = {t.upper() for t in args.tickers.split(",") if t.strip()}
        config.watchlist = {
            k: v for k, v in config.watchlist.items() if k in wanted
        } or config.watchlist

    store = None
    if config.history_enabled() and not args.no_save:
        store = HistoryStore(config.history_path())

    with console.status("[cyan]Gathering market chatter..."):
        engine = Engine(config, history=store)
        digest = engine.run()

    if config.llm.get("enabled"):
        digest.narrative = llm.synthesize(digest, config.llm)

    fmt = args.format
    if fmt == "json":
        text = render.to_json(digest)
        _emit(text, args.out, console)
    elif fmt == "markdown":
        text = render.to_markdown(digest)
        _emit(text, args.out, console)
    else:
        render.to_terminal(digest, console)
        if args.out:
            _write(args.out, render.to_markdown(digest))
            console.print(f"[dim]Markdown written to {args.out}[/dim]")

    for name, err in engine.errors.items():
        console.print(f"[yellow]! source '{name}' skipped: {err}[/yellow]", highlight=False)
    return 0


def _write(path: str, text: str) -> None:
    dest = Path(path)
    if dest.parent != Path(""):
        dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(text, encoding="utf-8")


def _emit(text: str, out: str | None, console: Console) -> None:
    if out:
        _write(out, text)
        console.print(f"[dim]Written to {out}[/dim]")
    else:
        print(text)


def _cmd_sources(args: argparse.Namespace) -> int:
    console = Console()
    config = Config.load(args.config)
    console.print("[bold]Registered sources[/bold] (all free, no API key):\n")
    for name, cls in REGISTRY.items():
        enabled = config.sources.get(name, {}).get("enabled", False)
        weight = config.source_weight(name)
        mark = "[green]on[/green]" if enabled else "[dim]off[/dim]"
        doc = (cls.__doc__ or "").strip().splitlines()
        desc = doc[0] if doc else ""
        console.print(f"  {name:<12} {mark:<18} weight={weight}  [dim]{desc}[/dim]")
    return 0


def _cmd_doctor(args: argparse.Namespace) -> int:
    """Report what will and won't work in the current environment."""
    console = Console()
    config = Config.load(args.config)
    console.print(f"[bold]FinTechFeed {__version__}[/bold] — environment check\n")
    console.print(f"  config: {config.path or 'built-in defaults'}")
    console.print(f"  watchlist: {', '.join(config.watchlist) or '(empty)'}")
    console.print(f"  enabled sources: {', '.join(config.enabled_sources()) or '(none)'}\n")

    # Live connectivity probe per enabled source.
    sources = build_sources(config.enabled_sources(), config.sources)
    probe = {"NVDA": ["Nvidia"]}
    for src in sources:
        try:
            got = src.fetch(probe)
            console.print(f"  [green]ok[/green]   {src.name}: fetched {len(got)} items")
        except Exception as exc:
            console.print(f"  [red]fail[/red] {src.name}: {exc}")

    store = HistoryStore(config.history_path())
    runs = len(store.records()) if config.history_enabled() else 0
    console.print(
        f"  history: {'[green]on[/green]' if config.history_enabled() else '[dim]off[/dim]'} "
        f"({config.history_path()}, {runs} run{'s' if runs != 1 else ''} recorded)"
    )

    llm_ok = llm.available(config.llm)
    console.print(
        f"\n  LLM synthesis: {'[green]available[/green]' if llm_ok else '[dim]off[/dim]'} "
        f"(set llm.enabled + ANTHROPIC_API_KEY + install extras to enable)"
    )
    return 0


def _cmd_history(args: argparse.Namespace) -> int:
    """Show recorded sentiment history — the day-over-day trend per ticker."""
    console = Console()
    config = Config.load(args.config)
    store = HistoryStore(config.history_path())
    records = store.records()
    if not records:
        console.print(
            "[yellow]No sentiment history yet — run [bold]fintechfeed digest[/bold] "
            "first (history is on by default).[/yellow]"
        )
        return 0

    recent = records[-args.limit :]

    if args.ticker:
        t = args.ticker.upper()
        console.print(f"[bold]{t}[/bold] — sentiment history (last {len(recent)} runs)\n")
        prev: float | None = None
        seen = False
        for rec in recent:
            snap = rec.get("tickers", {}).get(t)
            if not snap:
                continue
            seen = True
            score = snap["score"]
            style = {"Bullish": "green", "Bearish": "red"}.get(snap["label"], "yellow")
            change = "" if prev is None else f"  [dim]({score - prev:+.2f})[/dim]"
            console.print(
                f"  {rec['date']}  [{style}]{score:+.2f}  {snap['label']}[/{style}]{change}"
            )
            prev = score
        if not seen:
            console.print(f"[yellow]No history for {t}.[/yellow]")
        return 0

    # Matrix view: one row per run, one column per ticker in the latest run.
    tickers = sorted(recent[-1].get("tickers", {}))
    table = Table(show_header=True, header_style="bold")
    table.add_column("Run (UTC)")
    for t in tickers:
        table.add_column(t, justify="right")
    for rec in recent:
        cells = [rec.get("date", "?")]
        snaps = rec.get("tickers", {})
        for t in tickers:
            snap = snaps.get(t)
            cells.append(f"{snap['score']:+.2f}" if snap else "[dim]—[/dim]")
        table.add_row(*cells)
    console.print(table)
    console.print("[dim]Tip: fintechfeed history --ticker NVDA for one name's trend.[/dim]")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fintechfeed",
        description="Aggregate market chatter and score finance-tuned sentiment per ticker.",
    )
    parser.add_argument("--version", action="version", version=f"fintechfeed {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    d = sub.add_parser("digest", help="run a research pass and print the digest")
    d.add_argument("--config", help="path to config.yaml")
    d.add_argument("--tickers", help="comma-separated subset of the watchlist, e.g. NVDA,BTC")
    d.add_argument("--format", choices=["terminal", "markdown", "json"], default="terminal")
    d.add_argument("--out", help="write output to this file instead of stdout")
    d.add_argument(
        "--no-save",
        action="store_true",
        help="don't record this run in the local sentiment history",
    )
    d.set_defaults(func=_cmd_digest)

    s = sub.add_parser("sources", help="list registered sources and their status")
    s.add_argument("--config", help="path to config.yaml")
    s.set_defaults(func=_cmd_sources)

    doc = sub.add_parser("doctor", help="check the environment and probe each source")
    doc.add_argument("--config", help="path to config.yaml")
    doc.set_defaults(func=_cmd_doctor)

    h = sub.add_parser("history", help="show recorded day-over-day sentiment history")
    h.add_argument("--config", help="path to config.yaml")
    h.add_argument("--ticker", help="show the trend for a single ticker")
    h.add_argument("--limit", type=int, default=10, help="how many recent runs to show")
    h.set_defaults(func=_cmd_history)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
