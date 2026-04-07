"""Typer CLI entry point: generate, discover, config commands."""

from __future__ import annotations

import json
import os
from datetime import date, timedelta
from pathlib import Path
from typing import Annotated, Any

import typer
from rich.console import Console
from rich.table import Table

from gitvisual.config import Config, get_config_path, load_config, write_example_config
from gitvisual.git.collector import (
    GitCollectorError,
    collect_day,
    discover_repos,
    is_git_repo,
)
from gitvisual.llm.summarizer import make_summarizer
from gitvisual.render.card import CardRenderer
from gitvisual.render.themes import Palette, resolve_font_paths

app = typer.Typer(
    name="gitvisual",
    help="Generate beautiful visual cards from git commit history.",
    add_completion=False,
)

console = Console(stderr=True)
out_rich = Console()  # stdout for Rich-rendered output (config show table)


# stdout: machine-readable (plain print, no Rich wrapping/markup)
def _out(s: str) -> None:
    print(s)  # noqa: T201


def _out_json(data: Any) -> None:
    """Emit JSON to stdout."""
    print(json.dumps(data, indent=2))  # noqa: T201


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_renderer(config: Config) -> CardRenderer:
    palette = Palette.from_theme(config.theme)
    fonts = resolve_font_paths(
        font_regular=config.render.font_regular,
        font_mono=config.render.font_mono,
    )
    return CardRenderer(config=config.render, palette=palette, fonts=fonts)


def _parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError:
        console.print(f"[red]Invalid date '{value}'. Use YYYY-MM-DD format.[/red]")
        raise typer.Exit(1) from None


def _output_path(
    base_dir: Path,
    repo_name: str,
    target_date: date,
) -> Path:
    filename = f"{target_date.isoformat()}_{repo_name}.png"
    return base_dir / filename


# ---------------------------------------------------------------------------
# generate command
# ---------------------------------------------------------------------------


@app.command()
def generate(
    repos: Annotated[
        list[Path] | None,
        typer.Argument(help="Repository path(s) to generate cards for."),
    ] = None,
    date_str: Annotated[
        str | None,
        typer.Option("--date", "-d", help="Target date (YYYY-MM-DD). Defaults to today."),
    ] = None,
    yesterday: Annotated[
        bool,
        typer.Option("--yesterday", help="Use yesterday's date."),
    ] = False,
    date_from: Annotated[
        str | None,
        typer.Option("--from", help="Start of date range (YYYY-MM-DD)."),
    ] = None,
    date_to: Annotated[
        str | None,
        typer.Option("--to", help="End of date range (YYYY-MM-DD). Defaults to --from."),
    ] = None,
    last_week: Annotated[
        bool,
        typer.Option("--last-week", help="Generate cards for the last 7 days."),
    ] = False,
    discover_path: Annotated[
        Path | None,
        typer.Option(
            "--discover",
            help="Discover repos under this path instead of specifying them explicitly.",
        ),
    ] = None,
    output: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="Output directory (default: current dir)."),
    ] = None,
    summarize: Annotated[
        bool,
        typer.Option("--summarize/--no-summary", help="Enable LLM summary generation."),
    ] = False,
    style: Annotated[
        str | None,
        typer.Option("--style", help="Card style: compact | detailed"),
    ] = None,
    config_path: Annotated[
        Path | None,
        typer.Option("--config", help="Path to config.toml"),
    ] = None,
    stub_llm: Annotated[
        bool,
        typer.Option("--stub-llm", hidden=True, help="Use stub LLM (for testing)."),
    ] = False,
    model: Annotated[
        str | None,
        typer.Option(
            "--model", "-m", help="LLM model override (e.g. openrouter/openai/gpt-4o-mini)."
        ),
    ] = None,
    max_tokens: Annotated[
        int | None,
        typer.Option("--max-tokens", help="Override max_tokens for LLM calls."),
    ] = None,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Output results as JSON to stdout (for scripts/agents)."),
    ] = False,
) -> None:
    """Generate visual cards from git commit history."""
    # Validate: repos and --discover are mutually exclusive; one must be provided
    if repos and discover_path:
        console.print(
            "[red]Error:[/red] Cannot specify repos and --discover together — they are mutually exclusive."
        )
        raise typer.Exit(1)
    if not repos and not discover_path:
        console.print("[red]Error:[/red] Specify at least one repo path, or use --discover PATH.")
        raise typer.Exit(1)
    if not repos and not discover_path:
        console.print("[red]Error:[/red] Specify at least one repo path, or use --discover PATH.")
        raise typer.Exit(1)

    config = load_config(config_path)

    # Resolve date range
    today = date.today()
    if last_week:
        d_from = today - timedelta(days=6)
        d_to = today
    elif date_from:
        d_from = _parse_date(date_from)
        d_to = _parse_date(date_to) if date_to else d_from
    elif yesterday:
        d_from = d_to = today - timedelta(days=1)
    elif date_str:
        d_from = d_to = _parse_date(date_str)
    else:
        d_from = d_to = today

    # Resolve output dir
    out_dir = output or Path(config.defaults.output_dir)
    out_dir = out_dir.expanduser().resolve()

    # Resolve repo list — either explicit or discovered
    resolved_repos: list[Path]
    if discover_path:
        search = discover_path.expanduser().resolve()
        console.print(f"Discovering repos under [bold]{search}[/bold]…")
        resolved_repos = discover_repos(search, exclude=config.repos.exclude)
        if not resolved_repos:
            console.print(f"[yellow]No git repositories found under {search}[/yellow]")
            raise typer.Exit(0)
    else:
        resolved_repos = list(repos or [])

    # Build renderer (allow style override)

    render_cfg = config.render
    if style:
        render_cfg = render_cfg.model_copy(update={"style": style})
        # Rebuild config with updated render
        config = Config(
            defaults=config.defaults,
            llm=config.llm,
            render=render_cfg,
            repos=config.repos,
            theme=config.theme,
        )

    renderer = _make_renderer(config)

    # Load .env file early so our pre-flight check and the summarizer see the same env
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass

    summarizer = make_summarizer(
        enabled=summarize,
        model=model or config.llm.model,
        api_key_env=config.llm.api_key_env,
        api_base=config.llm.api_base,
        max_tokens=max_tokens if max_tokens is not None else config.llm.max_tokens,
        max_tokens_grouping=config.llm.max_tokens_grouping,
        timeout=config.llm.timeout,
        stub=stub_llm,
    )

    # Pre-flight: warn if --summarize requested but API key is missing
    if summarize and not stub_llm:
        key_var = config.llm.api_key_env
        if not os.environ.get(key_var):
            console.print(
                f"[yellow]Warning:[/yellow] --summarize requested but ${key_var} is not set. "
                f"Summaries will be skipped.\n"
                f"  Set it with: export {key_var}=<your-key>\n"
                f"  Model: {config.llm.model}\n"
                f"  Run [bold]gitvisual config show[/bold] to review LLM settings."
            )

    current = d_from
    total_cards = 0
    total_summaries = 0
    results: list[dict[str, Any]] = []
    from datetime import timedelta as td

    while current <= d_to:
        for repo_path in resolved_repos:
            repo_path = repo_path.expanduser().resolve()
            if not is_git_repo(repo_path):
                console.print(f"[yellow]Skipping {repo_path}: not a git repo[/yellow]")
                continue
            try:
                day = collect_day(repo_path, current)
                if day.is_empty:
                    if not discover_path:
                        console.print(f"[dim]{current}  {day.repo_name}: no commits[/dim]")
                    continue

                if summarize or stub_llm:
                    summary = summarizer.summarize(day)
                    if summary:
                        day = day.model_copy(update={"summary": summary})
                        total_summaries += 1
                    groups = summarizer.group_commits(
                        day, max_groups=config.render.max_groups_shown
                    )
                    if groups is not None:
                        day = day.model_copy(update={"commit_groups": groups})

                card_path = _output_path(out_dir, day.repo_name, current)
                renderer.render_to_file(day, card_path)
                summary_preview = f" — [italic]{day.summary}[/italic]" if day.summary else ""
                console.print(
                    f"[green]✓[/green]  {current}  {day.repo_name}: "
                    f"{len(day.commits)} commit(s) → {card_path}{summary_preview}"
                )
                total_cards += 1
                results.append(
                    {
                        "date": current.isoformat(),
                        "repo": day.repo_name,
                        "repo_path": str(repo_path),
                        "commits": len(day.commits),
                        "card_path": str(card_path),
                        "summary": day.summary,
                        "commit_groups": [
                            {
                                "summary": g.summary,
                                "insertions": g.total_insertions,
                                "deletions": g.total_deletions,
                                "files_changed": g.total_files_changed,
                                "commits": [
                                    {"hash": c.short_hash, "message": c.message} for c in g.commits
                                ],
                            }
                            for g in day.commit_groups
                        ]
                        if day.commit_groups is not None
                        else None,
                    }
                )
                if not json_output:
                    _out(str(card_path))

            except GitCollectorError as e:
                console.print(f"[red]Error collecting {repo_path}: {e}[/red]")

        current += td(days=1)

    if json_output:
        _out_json(results)

    if total_cards == 0:
        console.print("[dim]No cards generated.[/dim]")

    if summarize and not stub_llm and total_cards > 0 and total_summaries == 0:
        console.print(
            "\n[yellow]No LLM summaries were generated.[/yellow] "
            f"Check that ${config.llm.api_key_env} is set and the model "
            f"[bold]{config.llm.model}[/bold] is reachable.\n"
            "  Run [bold]gitvisual config show[/bold] to review LLM settings."
        )


# ---------------------------------------------------------------------------
# discover command
# ---------------------------------------------------------------------------


@app.command()
def discover(
    search_path: Annotated[
        Path,
        typer.Argument(help="Directory to search for git repositories."),
    ],
    date_str: Annotated[
        str | None,
        typer.Option("--date", "-d", help="Check for activity on this date (YYYY-MM-DD)."),
    ] = None,
    yesterday: Annotated[
        bool,
        typer.Option("--yesterday", help="Use yesterday's date."),
    ] = False,
    config_path: Annotated[
        Path | None,
        typer.Option("--config", help="Path to config.toml"),
    ] = None,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Output results as JSON to stdout (for scripts/agents)."),
    ] = False,
) -> None:
    """Find git repositories with commit activity on a given date."""
    config = load_config(config_path)

    today = date.today()
    if yesterday:
        target = today - timedelta(days=1)
    elif date_str:
        target = _parse_date(date_str)
    else:
        target = today

    search_path = search_path.expanduser().resolve()
    repos = discover_repos(search_path, exclude=config.repos.exclude)

    if not repos:
        console.print(f"[yellow]No git repositories found under {search_path}[/yellow]")
        raise typer.Exit(0)

    console.print(
        f"Found [bold]{len(repos)}[/bold] repositories. Checking for activity on {target}…\n"
    )

    results: list[dict[str, Any]] = []
    for repo_path in repos:
        try:
            day = collect_day(repo_path, target)
            if not day.is_empty:
                console.print(f"[green]✓[/green]  {day.repo_name}: {len(day.commits)} commit(s)")
                results.append(
                    {
                        "date": target.isoformat(),
                        "repo": day.repo_name,
                        "repo_path": str(repo_path),
                        "commits": len(day.commits),
                    }
                )
                if not json_output:
                    _out(str(repo_path))
        except GitCollectorError:
            pass

    if not results:
        console.print(f"\n[dim]No activity found on {target}.[/dim]")
        raise typer.Exit(0)

    if json_output:
        _out_json(results)

    console.print(f"\n[bold]{len(results)}[/bold] active repos on {target}.")
    console.print(
        f"\n[dim]Tip: run [bold]gitvisual generate --discover {search_path}[/bold] to generate cards.[/dim]"
    )


# ---------------------------------------------------------------------------
# config command group
# ---------------------------------------------------------------------------


config_app = typer.Typer(name="config", help="Manage gitvisual configuration.")
app.add_typer(config_app)


@config_app.command("init")
def config_init(
    path: Annotated[
        Path | None,
        typer.Option("--path", help="Write config to this path instead of the default."),
    ] = None,
    force: Annotated[
        bool,
        typer.Option("--force", help="Overwrite existing config."),
    ] = False,
) -> None:
    """Create a default config.toml."""
    target = path or get_config_path()
    if target.exists() and not force:
        console.print(
            f"[yellow]Config already exists at {target}. Use --force to overwrite.[/yellow]"
        )
        raise typer.Exit(1)
    write_example_config(target)
    console.print(f"[green]✓[/green]  Config written to {target}")


@config_app.command("show")
def config_show(
    config_path: Annotated[
        Path | None,
        typer.Option("--config", help="Path to config.toml"),
    ] = None,
) -> None:
    """Show the current configuration."""
    path = config_path or get_config_path()
    config = load_config(path)

    table = Table(title=f"Config: {path}", show_header=True)
    table.add_column("Section", style="cyan")
    table.add_column("Key", style="white")
    table.add_column("Value", style="green")

    for section, obj in [
        ("defaults", config.defaults),
        ("llm", config.llm),
        ("render", config.render),
        ("repos", config.repos),
        ("theme", config.theme),
    ]:
        for key, value in obj.model_dump().items():
            table.add_row(section, key, str(value))

    out_rich.print(table)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    app()


if __name__ == "__main__":
    main()
