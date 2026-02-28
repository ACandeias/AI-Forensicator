"""AIFT export: CSV, JSON, JSONL, and Markdown report generation."""

import csv
import json
import os
import sys
from datetime import datetime, timezone
from typing import List, Optional

# Allow imports from the project root.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import db
from schema import AIArtifact

# Import sibling analyzer modules.
from analyzers import stats as stats_mod
from analyzers.timeline import find_gaps


# Columns to include in flat-file exports.
_EXPORT_FIELDS = [
    "id", "source_tool", "artifact_type", "timestamp", "file_path",
    "file_hash_sha256", "file_size_bytes", "file_modified", "file_created",
    "user", "hostname", "content_preview", "model_identified",
    "conversation_id", "message_role", "token_estimate", "metadata",
    "collection_timestamp",
]


def _resolve_artifacts(
    artifacts: Optional[List[AIArtifact]] = None,
    source_filter: Optional[str] = None,
) -> List[AIArtifact]:
    """Return the artifact list to export.

    If *artifacts* is provided it is used directly (with optional source
    filtering).  Otherwise all artifacts are fetched from the database.
    """
    if artifacts is None:
        artifacts = db.query_artifacts(source_tool=source_filter, limit=100000)
    elif source_filter:
        artifacts = [a for a in artifacts if a.source_tool == source_filter]
    return artifacts


def _artifact_row(artifact: AIArtifact) -> List[str]:
    """Flatten an artifact into a list of string values matching ``_EXPORT_FIELDS``."""
    d = artifact.to_dict()
    row = []  # type: List[str]
    for f in _EXPORT_FIELDS:
        val = d.get(f)
        row.append("" if val is None else str(val))
    return row


# ------------------------------------------------------------------
# CSV
# ------------------------------------------------------------------

def export_csv(
    output_path: str,
    artifacts: Optional[List[AIArtifact]] = None,
    source_filter: Optional[str] = None,
) -> str:
    """Export artifacts to a CSV file.

    Parameters
    ----------
    output_path : str
        Destination file path.
    artifacts : list, optional
        Pre-fetched artifacts.  When *None* all artifacts are queried from DB.
    source_filter : str, optional
        Restrict to a single ``source_tool`` value.

    Returns
    -------
    str
        The absolute path of the written file.
    """
    items = _resolve_artifacts(artifacts, source_filter)
    output_path = os.path.abspath(output_path)
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    with open(output_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(_EXPORT_FIELDS)
        for a in items:
            writer.writerow(_artifact_row(a))

    return output_path


# ------------------------------------------------------------------
# JSON
# ------------------------------------------------------------------

def export_json(
    output_path: str,
    artifacts: Optional[List[AIArtifact]] = None,
    source_filter: Optional[str] = None,
) -> str:
    """Export artifacts as a JSON array.

    Returns the absolute path of the written file.
    """
    items = _resolve_artifacts(artifacts, source_filter)
    output_path = os.path.abspath(output_path)
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    records = [a.to_dict() for a in items]
    with open(output_path, "w", encoding="utf-8") as fh:
        json.dump(records, fh, indent=2, default=str)

    return output_path


# ------------------------------------------------------------------
# JSONL
# ------------------------------------------------------------------

def export_jsonl(
    output_path: str,
    artifacts: Optional[List[AIArtifact]] = None,
    source_filter: Optional[str] = None,
) -> str:
    """Export artifacts as newline-delimited JSON (JSONL).

    Returns the absolute path of the written file.
    """
    items = _resolve_artifacts(artifacts, source_filter)
    output_path = os.path.abspath(output_path)
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as fh:
        for a in items:
            fh.write(json.dumps(a.to_dict(), default=str) + "\n")

    return output_path


# ------------------------------------------------------------------
# Markdown Report
# ------------------------------------------------------------------

def _md_escape(text: str) -> str:
    """Escape pipe characters and HTML tags for safe Markdown table cells."""
    text = text.replace("|", "\\|")
    text = text.replace("<", "&lt;").replace(">", "&gt;")
    return text


def _md_table(headers: List[str], rows: List[List[str]]) -> str:
    """Build a simple Markdown table."""
    lines = []  # type: List[str]
    lines.append("| " + " | ".join(_md_escape(h) for h in headers) + " |")
    lines.append("| " + " | ".join(["---"] * len(headers)) + " |")
    for row in rows:
        lines.append("| " + " | ".join(_md_escape(c) for c in row) + " |")
    return "\n".join(lines)


def export_report(output_path: str) -> str:
    """Generate a Markdown forensic report.

    The report includes:
    * Title and generation timestamp
    * Summary statistics
    * Tool (source) breakdown table
    * Model usage table
    * Timeline overview (date range and significant gaps)
    * Chain-of-custody metadata (hostname, user, collection runs)

    Returns the absolute path of the written file.
    """
    output_path = os.path.abspath(output_path)
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    # Gather data -------------------------------------------------------
    summary = stats_mod.compute_summary_stats()
    tool_dist = stats_mod.compute_tool_distribution()
    model_usage = stats_mod.compute_model_usage()
    token_info = stats_mod.compute_token_estimates()
    gaps = find_gaps(min_gap_hours=4)
    runs = db.get_collection_runs(limit=50)

    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    # Assemble Markdown -------------------------------------------------
    sections = []  # type: List[str]

    # Title
    sections.append("# AI Forensics Report")
    sections.append("")
    sections.append("**Generated:** {}".format(now_iso))
    sections.append("")

    # Summary stats
    sections.append("## Summary Statistics")
    sections.append("")
    date_range = summary["date_range"]
    dr_start = date_range[0] if date_range[0] else "N/A"
    dr_end = date_range[1] if date_range[1] else "N/A"
    sections.append("| Metric | Value |")
    sections.append("| --- | --- |")
    sections.append("| Total Artifacts | {} |".format(summary["total_artifacts"]))
    sections.append("| Unique Sources | {} |".format(summary["unique_sources"]))
    sections.append("| Unique Artifact Types | {} |".format(summary["unique_types"]))
    sections.append("| Date Range | {} to {} |".format(dr_start, dr_end))
    sections.append("| Total Token Estimate | {} |".format(summary["total_tokens"]))
    sections.append("")

    # Tool breakdown
    sections.append("## Tool Breakdown")
    sections.append("")
    if tool_dist:
        tool_rows = [[name, str(count)] for name, count in tool_dist]
        sections.append(_md_table(["Source Tool", "Artifacts"], tool_rows))
    else:
        sections.append("_No data._")
    sections.append("")

    # Model usage
    sections.append("## Model Usage")
    sections.append("")
    if model_usage:
        model_rows = [[name, str(count)] for name, count in model_usage]
        sections.append(_md_table(["Model", "Artifacts"], model_rows))
    else:
        sections.append("_No model data identified._")
    sections.append("")

    # Token estimates by source & model
    sections.append("## Token Estimates")
    sections.append("")
    sections.append("**Total tokens:** {}".format(token_info["total_tokens"]))
    sections.append("")
    if token_info["by_source"]:
        ts_rows = [[src, str(tok)] for src, tok in sorted(
            token_info["by_source"].items(), key=lambda x: x[1], reverse=True
        )]
        sections.append("### By Source")
        sections.append("")
        sections.append(_md_table(["Source", "Tokens"], ts_rows))
        sections.append("")
    if token_info["by_model"]:
        tm_rows = [[mdl, str(tok)] for mdl, tok in sorted(
            token_info["by_model"].items(), key=lambda x: x[1], reverse=True
        )]
        sections.append("### By Model")
        sections.append("")
        sections.append(_md_table(["Model", "Tokens"], tm_rows))
        sections.append("")

    # Timeline overview
    sections.append("## Timeline Overview")
    sections.append("")
    sections.append("**Date range:** {} to {}".format(dr_start, dr_end))
    sections.append("")
    if gaps:
        sections.append("### Significant Gaps (>= 4 hours)")
        sections.append("")
        gap_rows = [[g[0], g[1], "{:.2f}".format(g[2])] for g in gaps]
        sections.append(_md_table(["Gap Start", "Gap End", "Hours"], gap_rows))
    else:
        sections.append("_No significant timeline gaps detected._")
    sections.append("")

    # Chain of custody
    sections.append("## Chain of Custody")
    sections.append("")
    if runs:
        # Collect unique hostnames and usernames across runs
        hostnames = sorted(set(r.get("hostname") or "unknown" for r in runs))
        usernames = sorted(set(r.get("username") or "unknown" for r in runs))
        sections.append("**Hostnames:** {}".format(", ".join(hostnames)))
        sections.append("")
        sections.append("**Users:** {}".format(", ".join(usernames)))
        sections.append("")
        sections.append("### Collection Runs ({})".format(len(runs)))
        sections.append("")
        run_rows = []  # type: List[List[str]]
        for r in runs:
            run_rows.append([
                r.get("id", "")[:8] + "...",
                r.get("start_time", "N/A"),
                r.get("end_time", "N/A") or "in-progress",
                str(r.get("total_artifacts", 0)),
                r.get("hostname", "N/A") or "N/A",
                r.get("username", "N/A") or "N/A",
            ])
        sections.append(_md_table(
            ["Run ID", "Start", "End", "Artifacts", "Host", "User"],
            run_rows,
        ))
    else:
        sections.append("_No collection runs recorded._")
    sections.append("")

    # Write -------------------------------------------------------------
    with open(output_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(sections) + "\n")

    return output_path
