"""AIFT Rich-based interactive terminal menu."""

import json
import os
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime, timezone
from typing import Dict, List, Optional

# Allow imports from the project root.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.tree import Tree
from rich.prompt import Prompt, IntPrompt
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich.text import Text
from rich.markdown import Markdown
from rich.columns import Columns
from rich.layout import Layout

import db
from collectors import get_detected_collectors
from analyzers.timeline import build_timeline, timeline_by_day
from analyzers.stats import (
    compute_summary_stats, compute_tool_distribution,
    compute_model_usage, compute_daily_activity,
)
from analyzers.export import export_csv, export_json, export_jsonl, export_report
from schema import AIArtifact, CollectionRun
from config import APP_NAME, VERSION

console = Console()

# Color mapping for source tools
SOURCE_COLORS = {
    "claude_code": "bright_cyan",
    "claude_desktop": "cyan",
    "chatgpt": "bright_green",
    "cursor": "bright_magenta",
    "chrome": "yellow",
    "safari": "blue",
    "arc": "bright_red",
    "generic_logs": "white",
    "perplexity": "bright_blue",
    "codex": "bright_yellow",
    "copilot": "green",
}

PAGE_SIZE = 20


def _color_for_source(source: str) -> str:
    """Return a Rich color name for the given source tool."""
    return SOURCE_COLORS.get(source, "white")


def _show_banner() -> None:
    """Display the application banner."""
    banner = Text()
    banner.append(APP_NAME, style="bold bright_cyan")
    banner.append("  v{}".format(VERSION), style="dim")
    console.print(Panel(banner, border_style="bright_cyan"))


def _show_menu() -> str:
    """Display the main menu and return the user's choice."""
    menu_text = (
        "[bold bright_cyan]1[/] Run Collection\n"
        "[bold bright_cyan]2[/] Browse Artifacts\n"
        "[bold bright_cyan]3[/] Timeline View\n"
        "[bold bright_cyan]4[/] Statistics\n"
        "[bold bright_cyan]5[/] Search\n"
        "[bold bright_cyan]6[/] Export\n"
        "[bold bright_cyan]7[/] Collection History\n"
        "[bold bright_cyan]0[/] Exit"
    )
    console.print(Panel(menu_text, title="Main Menu", border_style="bright_cyan"))
    choice = Prompt.ask(
        "[bold]Select an option[/]",
        choices=["0", "1", "2", "3", "4", "5", "6", "7"],
        default="0",
    )
    return choice


# ---------------------------------------------------------------------------
# 1. Run Collection
# ---------------------------------------------------------------------------

def _handle_collection() -> None:
    """Run all detected collectors with a progress dashboard."""
    console.print("\n[bold]Detecting available collectors...[/]")
    collectors = get_detected_collectors()

    if not collectors:
        console.print("[yellow]No collectors detected on this system.[/]")
        return

    console.print("[green]Found {} collector(s):[/] {}".format(
        len(collectors),
        ", ".join(c.name for c in collectors),
    ))

    run = CollectionRun(
        hostname=collectors[0]._hostname if collectors else None,
        username=collectors[0]._user if collectors else None,
    )
    all_artifacts = []  # type: List[AIArtifact]
    errors = []  # type: List[str]
    collector_names = []  # type: List[str]

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("{task.completed}/{task.total}"),
        console=console,
    ) as progress:
        overall = progress.add_task("Collecting artifacts", total=len(collectors))

        for collector in collectors:
            task_id = progress.add_task(
                "  {} ...".format(collector.name), total=1
            )
            collector_names.append(collector.name)
            try:
                artifacts = collector.collect()
                all_artifacts.extend(artifacts)
                progress.update(
                    task_id,
                    completed=1,
                    description="  {} - [green]{} artifacts[/]".format(
                        collector.name, len(artifacts)
                    ),
                )
            except (OSError, IOError, ValueError, TypeError, KeyError,
                    AttributeError, sqlite3.Error, json.JSONDecodeError) as exc:
                err_msg = "{}: {}".format(collector.name, exc)
                errors.append(err_msg)
                progress.update(
                    task_id,
                    completed=1,
                    description="  {} - [red]ERROR: {}[/]".format(
                        collector.name, exc
                    ),
                )
            progress.advance(overall)

    # Batch insert
    if all_artifacts:
        count = db.insert_artifacts_batch(all_artifacts)
        console.print(
            "\n[bold green]Inserted {} artifacts into the database.[/]".format(count)
        )
    else:
        console.print("\n[yellow]No artifacts collected.[/]")

    # Record the run
    run.end_time = datetime.now(timezone.utc).isoformat()
    run.collectors_run = json.dumps(collector_names)
    run.total_artifacts = len(all_artifacts)
    if errors:
        run.errors = json.dumps(errors)
    db.insert_run(run)

    if errors:
        console.print("[bold red]Errors during collection:[/]")
        for e in errors:
            console.print("  [red]- {}[/]".format(e))


# ---------------------------------------------------------------------------
# 2. Browse Artifacts
# ---------------------------------------------------------------------------

def _handle_browse() -> None:
    """Paginated artifact browser with drill-down detail."""
    offset = 0
    while True:
        artifacts = db.query_artifacts(limit=PAGE_SIZE, offset=offset)
        if not artifacts:
            console.print("[yellow]No artifacts found.[/]")
            break

        table = Table(
            title="Artifacts ({}-{})".format(offset + 1, offset + len(artifacts)),
            show_lines=True,
        )
        table.add_column("#", style="dim", width=4)
        table.add_column("Timestamp", style="cyan", width=20)
        table.add_column("Source", style="green", width=16)
        table.add_column("Type", style="magenta", width=16)
        table.add_column("Model", style="yellow", width=18)
        table.add_column("Preview", width=50)

        for i, a in enumerate(artifacts):
            table.add_row(
                str(offset + i + 1),
                (a.timestamp or "")[:19],
                a.source_tool,
                a.artifact_type,
                a.model_identified or "",
                (a.content_preview or "")[:50],
            )

        console.print(table)

        action = Prompt.ask(
            "[n]ext / [p]rev / [d]etail <#> / [b]ack",
            default="b",
        )

        if action.lower() == "n":
            offset += PAGE_SIZE
        elif action.lower() == "p":
            offset = max(0, offset - PAGE_SIZE)
        elif action.lower().startswith("d"):
            parts = action.split()
            if len(parts) >= 2:
                try:
                    idx = int(parts[1]) - 1 - offset
                    if 0 <= idx < len(artifacts):
                        _show_artifact_detail(artifacts[idx])
                except (ValueError, IndexError):
                    console.print("[red]Invalid index.[/]")
        elif action.lower() == "b":
            break


def _show_artifact_detail(artifact: AIArtifact) -> None:
    """Show all fields for a single artifact."""
    d = artifact.to_dict()
    table = Table(title="Artifact Detail", show_header=False, show_lines=True)
    table.add_column("Field", style="bold cyan", width=24)
    table.add_column("Value", width=70)
    for key, value in d.items():
        val_str = str(value) if value is not None else "[dim]None[/dim]"
        if len(val_str) > 200:
            val_str = val_str[:200] + "..."
        table.add_row(key, val_str)
    console.print(table)
    Prompt.ask("[dim]Press Enter to continue[/dim]", default="")


# ---------------------------------------------------------------------------
# 3. Timeline View
# ---------------------------------------------------------------------------

def _handle_timeline() -> None:
    """Display artifacts grouped by day in a tree view."""
    grouped = timeline_by_day()
    if not grouped:
        console.print("[yellow]No timestamped artifacts found.[/]")
        return

    tree = Tree("[bold]Artifact Timeline[/]")

    for day in sorted(grouped.keys()):
        day_artifacts = grouped[day]
        day_branch = tree.add(
            "[bold bright_white]{} [dim]({} artifacts)[/dim][/]".format(day, len(day_artifacts))
        )
        for a in day_artifacts:
            color = _color_for_source(a.source_tool)
            time_part = (a.timestamp or "")[11:19]
            label = "[{}]{} [bold]{}[/bold] / {} {}[/{}]".format(
                color,
                time_part,
                a.source_tool,
                a.artifact_type,
                ("- " + (a.content_preview or "")[:60]) if a.content_preview else "",
                color,
            )
            day_branch.add(label)

    console.print(tree)


# ---------------------------------------------------------------------------
# 4. Statistics
# ---------------------------------------------------------------------------

def _handle_statistics() -> None:
    """Display summary statistics panels."""
    summary = compute_summary_stats()

    # Summary panel
    lines = []  # type: List[str]
    lines.append("Total Artifacts:   [bold]{}[/]".format(summary["total_artifacts"]))
    lines.append("Unique Sources:    [bold]{}[/]".format(summary["unique_sources"]))
    lines.append("Artifact Types:    [bold]{}[/]".format(summary["unique_types"]))
    lines.append("Token Estimate:    [bold]{:,}[/]".format(summary["total_tokens"]))
    date_min, date_max = summary["date_range"]
    lines.append("Date Range:        [bold]{} to {}[/]".format(
        date_min or "N/A", date_max or "N/A"
    ))
    console.print(Panel("\n".join(lines), title="Summary", border_style="bright_cyan"))

    # Tool distribution table
    dist = compute_tool_distribution()
    if dist:
        t = Table(title="Tool Distribution")
        t.add_column("Source Tool", style="green")
        t.add_column("Count", justify="right", style="bold")
        for source, count in dist:
            t.add_row(source, str(count))
        console.print(t)

    # Model usage table
    models = compute_model_usage()
    if models:
        t = Table(title="Model Usage")
        t.add_column("Model", style="yellow")
        t.add_column("Count", justify="right", style="bold")
        for model, count in models:
            t.add_row(model or "(unknown)", str(count))
        console.print(t)

    # Daily activity table
    activity = compute_daily_activity()
    if activity:
        t = Table(title="Daily Activity")
        t.add_column("Date", style="cyan")
        t.add_column("Artifacts", justify="right", style="bold")
        for day, count in activity.items():
            t.add_row(day, str(count))
        console.print(t)


# ---------------------------------------------------------------------------
# 5. Search
# ---------------------------------------------------------------------------

def _handle_search() -> None:
    """Prompt for a query and display matching artifacts."""
    query = Prompt.ask("[bold]Search query[/]")
    if not query.strip():
        console.print("[yellow]Empty query.[/]")
        return

    results = db.search_artifacts(query)
    if not results:
        console.print("[yellow]No results for '{}'.[/]".format(query))
        return

    table = Table(title="Search Results ({} match{})".format(
        len(results), "es" if len(results) != 1 else ""
    ))
    table.add_column("#", style="dim", width=4)
    table.add_column("Timestamp", style="cyan", width=20)
    table.add_column("Source", style="green", width=16)
    table.add_column("Type", style="magenta", width=16)
    table.add_column("Preview", width=60)

    for i, a in enumerate(results):
        preview = (a.content_preview or a.file_path or "")[:60]
        # Highlight the query term in the preview
        highlighted = Text(preview)
        highlighted.highlight_words([query], style="bold red on white")
        table.add_row(
            str(i + 1),
            (a.timestamp or "")[:19],
            a.source_tool,
            a.artifact_type,
            highlighted,
        )

    console.print(table)


# ---------------------------------------------------------------------------
# 6. Export
# ---------------------------------------------------------------------------

def _handle_export() -> None:
    """Prompt for export format and output path, then export."""
    supported = ("csv", "json", "jsonl", "report")
    fmt = Prompt.ask(
        "[bold]Export format[/]",
        choices=list(supported),
        default="json",
    )
    output = Prompt.ask("[bold]Output file path[/]", default="aift_export.{}".format(fmt))

    _exporters = {
        "csv": export_csv,
        "json": export_json,
        "jsonl": export_jsonl,
        "report": export_report,
    }

    try:
        exporter = _exporters[fmt]
        result_path = exporter(output)
        console.print(
            "[bold green]Exported to {}[/]".format(result_path)
        )
    except (OSError, IOError, ValueError, sqlite3.Error) as exc:
        console.print("[bold red]Export failed: {}[/]".format(exc))


# ---------------------------------------------------------------------------
# 7. Collection History
# ---------------------------------------------------------------------------

def _handle_history() -> None:
    """Show past collection runs."""
    runs = db.get_collection_runs()
    if not runs:
        console.print("[yellow]No collection runs recorded.[/]")
        return

    table = Table(title="Collection History")
    table.add_column("ID", style="dim", width=10)
    table.add_column("Start", style="cyan", width=22)
    table.add_column("End", style="cyan", width=22)
    table.add_column("Collectors", style="green", width=30)
    table.add_column("Artifacts", justify="right", style="bold", width=10)
    table.add_column("Errors", style="red", width=10)

    for run in runs:
        collectors_str = ""
        if run.get("collectors_run"):
            try:
                names = json.loads(run["collectors_run"])
                collectors_str = ", ".join(names)
            except (json.JSONDecodeError, TypeError):
                collectors_str = str(run["collectors_run"])

        error_count = "0"
        if run.get("errors"):
            try:
                err_list = json.loads(run["errors"])
                error_count = str(len(err_list))
            except (json.JSONDecodeError, TypeError):
                error_count = "?"

        table.add_row(
            (run.get("id") or "")[:8],
            (run.get("start_time") or "")[:19],
            (run.get("end_time") or "")[:19],
            collectors_str,
            str(run.get("total_artifacts", 0)),
            error_count,
        )

    console.print(table)


# ---------------------------------------------------------------------------
# Main interactive loop
# ---------------------------------------------------------------------------

_HANDLERS = {
    "1": _handle_collection,
    "2": _handle_browse,
    "3": _handle_timeline,
    "4": _handle_statistics,
    "5": _handle_search,
    "6": _handle_export,
    "7": _handle_history,
}


def interactive_menu() -> None:
    """Main interactive menu loop."""
    db.ensure_db()
    _show_banner()

    while True:
        try:
            choice = _show_menu()
            if choice == "0":
                console.print("[bold bright_cyan]Goodbye![/]")
                break
            handler = _HANDLERS.get(choice)
            if handler:
                handler()
            else:
                console.print("[red]Unknown option.[/]")
        except KeyboardInterrupt:
            console.print("\n[bold bright_cyan]Goodbye![/]")
            break
        except (OSError, IOError, ValueError, TypeError, KeyError,
                AttributeError, sqlite3.Error, json.JSONDecodeError) as exc:
            console.print("[bold red]Error: {}[/]".format(exc))


if __name__ == "__main__":
    interactive_menu()
