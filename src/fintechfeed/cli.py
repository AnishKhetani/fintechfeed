"""Command-line interface: ``fintechfeed digest | sources | doctor``."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from rich.console import Console

from . import __version__, llm, render
from .config import Config
from .engine import Engine
from .sources import REGISTRY, build_sources


def _cmd_digest(args: argparse.Namespace) -> int:
    console = Console()
    config = Config.load(args.config)

    if args.tickers:
        wanted = {t.upper() for t in args.tickers.split(",") if t.strip()}
        config.watchlist = {
            k: v for k, v in config.watchlist.items() if k in wanted
        } or config.watchlist

    with console.status("[cyan]Gathering market chatter..."):
        engine = Engine(config)
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

    llm_ok = llm.available(config.llm)
    console.print(
        f"\n  LLM synthesis: {'[green]available[/green]' if llm_ok else '[dim]off[/dim]'} "
        f"(set llm.enabled + ANTHROPIC_API_KEY + install extras to enable)"
    )
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
    d.set_defaults(func=_cmd_digest)

    s = sub.add_parser("sources", help="list registered sources and their status")
    s.add_argument("--config", help="path to config.yaml")
    s.set_defaults(func=_cmd_sources)

    doc = sub.add_parser("doctor", help="check the environment and probe each source")
    doc.add_argument("--config", help="path to config.yaml")
    doc.set_defaults(func=_cmd_doctor)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
