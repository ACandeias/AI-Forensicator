#!/usr/bin/env python3
"""AIFT - AI Forensics Tool: CLI entry point."""

import argparse
import json
import logging
import os
import sqlite3
import sys

# Ensure the project root is on sys.path so that sibling modules resolve.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import APP_NAME, VERSION
import db


logger = logging.getLogger("aift")


# ------------------------------------------------------------------
# CLI sub-command handlers (work without rich)
# ------------------------------------------------------------------

def _cmd_collect(args: argparse.Namespace) -> None:
    """Run collection (or dry-run detection)."""
    from collectors import get_all_collectors, get_detected_collectors
    from schema import CollectionRun
    from datetime import datetime, timezone

    if args.dry_run:
        print("Detecting available collectors...")
        detected = get_detected_collectors()
        if detected:
            for c in detected:
                print("  [detected] {}".format(c.name))
        else:
            print("  No collectors detected on this system.")
        all_cols = get_all_collectors()
        not_detected = [c for c in all_cols if not c.detect()]
        for c in not_detected:
            print("  [not found] {}".format(c.name))
        return

    detected = get_detected_collectors()
    if not detected:
        print("No collectors detected on this system.")
        return

    print("Running {} collector(s)...".format(len(detected)))
    all_artifacts = []
    errors = []
    collector_names = []

    for collector in detected:
        collector_names.append(collector.name)
        try:
            artifacts = collector.collect()
            all_artifacts.extend(artifacts)
            print("  {} - {} artifacts".format(collector.name, len(artifacts)))
        except (OSError, IOError, ValueError, TypeError, KeyError,
                AttributeError, sqlite3.Error, json.JSONDecodeError) as exc:
            err_msg = "{}: {}".format(collector.name, exc)
            errors.append(err_msg)
            print("  {} - ERROR: {}".format(collector.name, exc))
            if args.verbose:
                logger.exception("Collector %s failed", collector.name)

    if all_artifacts:
        count = db.insert_artifacts_batch(all_artifacts)
        print("Inserted {} artifacts.".format(count))
    else:
        print("No artifacts collected.")

    run = CollectionRun(
        end_time=datetime.now(timezone.utc).isoformat(),
        collectors_run=json.dumps(collector_names),
        total_artifacts=len(all_artifacts),
        errors=json.dumps(errors) if errors else None,
    )
    db.insert_run(run)

    if errors:
        print("Errors:")
        for e in errors:
            print("  - {}".format(e))


def _cmd_browse(args: argparse.Namespace) -> None:
    """Browse artifacts with optional filters."""
    capped_limit = min(args.limit, 100000)
    artifacts = db.query_artifacts(
        source_tool=args.source,
        artifact_type=args.type,
        limit=capped_limit,
    )
    if not artifacts:
        print("No artifacts found.")
        return

    print("{:<20s} {:<16s} {:<16s} {:<18s} {}".format(
        "Timestamp", "Source", "Type", "Model", "Preview"
    ))
    print("-" * 100)
    for a in artifacts:
        print("{:<20s} {:<16s} {:<16s} {:<18s} {}".format(
            (a.timestamp or "")[:19],
            a.source_tool,
            a.artifact_type,
            a.model_identified or "",
            (a.content_preview or "")[:40],
        ))


def _cmd_stats(args: argparse.Namespace) -> None:
    """Show summary statistics."""
    stats = db.get_stats()
    print("=== {} Statistics ===".format(APP_NAME))
    print("Total artifacts:  {}".format(stats["total_artifacts"]))
    print("Collection runs:  {}".format(stats["collection_runs"]))
    print("Token estimate:   {}".format(stats["total_token_estimate"]))

    date_min, date_max = stats["date_range"]
    print("Date range:       {} to {}".format(date_min or "N/A", date_max or "N/A"))

    if stats["by_source"]:
        print("\nSource distribution:")
        for source, count in stats["by_source"]:
            print("  {:<30s} {:>6d}".format(source, count))

    if stats["by_model"]:
        print("\nModel usage:")
        for model, count in stats["by_model"]:
            print("  {:<30s} {:>6d}".format(model or "(unknown)", count))


def _cmd_search(args: argparse.Namespace) -> None:
    """Search artifacts."""
    results = db.search_artifacts(args.query)
    if not results:
        print("No results for '{}'.".format(args.query))
        return

    print("Found {} result(s):".format(len(results)))
    print("{:<20s} {:<16s} {:<16s} {}".format(
        "Timestamp", "Source", "Type", "Preview"
    ))
    print("-" * 80)
    for a in results:
        print("{:<20s} {:<16s} {:<16s} {}".format(
            (a.timestamp or "")[:19],
            a.source_tool,
            a.artifact_type,
            (a.content_preview or a.file_path or "")[:40],
        ))


def _cmd_export(args: argparse.Namespace) -> None:
    """Export artifacts."""
    from analyzers.export import export_csv, export_json, export_jsonl, export_report

    fmt = args.format
    output = args.output

    exporters = {
        "csv": export_csv,
        "json": export_json,
        "jsonl": export_jsonl,
        "report": export_report,
    }

    exporter = exporters.get(fmt)
    if exporter is None:
        print("Unsupported format: {}. Choose from csv, json, jsonl, report.".format(fmt))
        sys.exit(1)

    result_path = exporter(output)
    print("Exported to {}".format(result_path))


def _cmd_timeline(args: argparse.Namespace) -> None:
    """Show timeline."""
    artifacts = db.get_timeline(
        start=args.start,
        end=args.end,
        source_tool=args.source,
    )
    if not artifacts:
        print("No timestamped artifacts found.")
        return

    current_day = None
    for a in artifacts:
        day = (a.timestamp or "")[:10]
        if day != current_day:
            current_day = day
            print("\n=== {} ===".format(day))
        time_part = (a.timestamp or "")[11:19]
        print("  {} [{:<14s}] {:<16s} {}".format(
            time_part,
            a.source_tool,
            a.artifact_type,
            (a.content_preview or "")[:50],
        ))


# ------------------------------------------------------------------
# Argument parser
# ------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="aift",
        description="{} v{}".format(APP_NAME, VERSION),
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Enable debug logging",
    )
    parser.add_argument(
        "--version", action="version",
        version="{} {}".format(APP_NAME, VERSION),
    )

    subparsers = parser.add_subparsers(dest="command")

    # collect
    sp_collect = subparsers.add_parser("collect", help="Run artifact collection")
    sp_collect.add_argument(
        "--dry-run", action="store_true",
        help="Detect collectors without collecting",
    )

    # browse
    sp_browse = subparsers.add_parser("browse", help="Browse collected artifacts")
    sp_browse.add_argument("--source", default=None, help="Filter by source tool")
    sp_browse.add_argument("--type", default=None, help="Filter by artifact type")
    sp_browse.add_argument("--limit", type=int, default=50,
                           help="Max results (capped at 100000)")

    # stats
    subparsers.add_parser("stats", help="Show summary statistics")

    # search
    sp_search = subparsers.add_parser("search", help="Search artifacts")
    sp_search.add_argument("query", help="Search query string")

    # export
    sp_export = subparsers.add_parser("export", help="Export artifacts")
    sp_export.add_argument(
        "format", choices=["csv", "json", "jsonl", "report"],
        help="Export format",
    )
    sp_export.add_argument("output", help="Output file path")

    # timeline
    sp_timeline = subparsers.add_parser("timeline", help="Show artifact timeline")
    sp_timeline.add_argument("--start", default=None, help="Start date (ISO)")
    sp_timeline.add_argument("--end", default=None, help="End date (ISO)")
    sp_timeline.add_argument("--source", default=None, help="Filter by source tool")

    return parser


# ------------------------------------------------------------------
# Entry point
# ------------------------------------------------------------------

_COMMAND_MAP = {
    "collect": _cmd_collect,
    "browse": _cmd_browse,
    "stats": _cmd_stats,
    "search": _cmd_search,
    "export": _cmd_export,
    "timeline": _cmd_timeline,
}


def main() -> None:
    """CLI entry point."""
    parser = build_parser()
    args = parser.parse_args()

    # Configure logging
    if args.verbose:
        logging.basicConfig(level=logging.DEBUG, format="%(levelname)s: %(message)s")
    else:
        logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")

    # Ensure the database exists
    db.ensure_db()

    # Dispatch to subcommand or interactive mode
    if args.command is None:
        # No subcommand: launch interactive mode (requires rich)
        try:
            from ui.terminal import interactive_menu
            interactive_menu()
        except ImportError:
            print("Interactive mode requires the 'rich' package.")
            print("Install it with: pip install rich")
            print("Or use a subcommand: aift collect | browse | stats | search | export | timeline")
            sys.exit(1)
    else:
        handler = _COMMAND_MAP.get(args.command)
        if handler:
            handler(args)
        else:
            parser.print_help()


if __name__ == "__main__":
    main()
