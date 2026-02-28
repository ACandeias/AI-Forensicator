"""AIFT timeline analysis: chronological ordering, grouping, and gap detection."""

import sys
import os
from collections import defaultdict
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

# Allow imports from the project root.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import db
from schema import AIArtifact


def _parse_ts(ts_str: str) -> datetime:
    """Parse an ISO-8601 timestamp string into a timezone-aware datetime.

    Handles both offset-aware (``+00:00`` / ``Z``) and naive strings.  Naive
    strings are assumed to be UTC.
    """
    cleaned = ts_str.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(cleaned)
    except ValueError:
        # Fallback: strip fractional seconds that Python 3.9 cannot parse
        dt = datetime.strptime(cleaned[:19], "%Y-%m-%dT%H:%M:%S")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def build_timeline(
    start: Optional[str] = None,
    end: Optional[str] = None,
    source_filter: Optional[str] = None,
) -> List[AIArtifact]:
    """Return artifacts sorted chronologically (ascending).

    Parameters
    ----------
    start : str, optional
        ISO-8601 lower-bound timestamp (inclusive).
    end : str, optional
        ISO-8601 upper-bound timestamp (inclusive).
    source_filter : str, optional
        Restrict to a single ``source_tool`` value.
    """
    artifacts = db.get_timeline(start=start, end=end, source_tool=source_filter)
    # db.get_timeline already sorts ASC, but we enforce the contract here in
    # case the underlying query changes.
    artifacts.sort(key=lambda a: a.timestamp or "")
    return artifacts


def timeline_by_day() -> Dict[str, List[AIArtifact]]:
    """Group all timestamped artifacts by calendar day (``YYYY-MM-DD``).

    Returns a dict mapping date strings to lists of :class:`AIArtifact`,
    sorted chronologically within each day.
    """
    artifacts = build_timeline()
    grouped = defaultdict(list)  # type: Dict[str, List[AIArtifact]]
    for artifact in artifacts:
        if artifact.timestamp:
            day_key = artifact.timestamp[:10]  # YYYY-MM-DD
            grouped[day_key].append(artifact)
    return dict(grouped)


def cross_tool_timeline() -> List[AIArtifact]:
    """Interleave artifacts from all source tools chronologically.

    This is semantically equivalent to :func:`build_timeline` without any
    source filter, ensuring that artifacts from *every* source appear in a
    single chronological stream.
    """
    return build_timeline()


def find_gaps(min_gap_hours: float = 4) -> List[Tuple[str, str, float]]:
    """Find significant time gaps between consecutive artifacts.

    Parameters
    ----------
    min_gap_hours : float
        Minimum gap duration (in hours) to report.  Defaults to 4.

    Returns
    -------
    list of (gap_start, gap_end, gap_hours)
        Each tuple contains the ISO timestamp of the artifact *before* the
        gap, the ISO timestamp of the artifact *after* the gap, and the gap
        duration in hours (rounded to two decimals).
    """
    artifacts = build_timeline()
    gaps = []  # type: List[Tuple[str, str, float]]
    for i in range(1, len(artifacts)):
        prev_ts = artifacts[i - 1].timestamp
        curr_ts = artifacts[i].timestamp
        if not prev_ts or not curr_ts:
            continue
        prev_dt = _parse_ts(prev_ts)
        curr_dt = _parse_ts(curr_ts)
        delta_hours = (curr_dt - prev_dt).total_seconds() / 3600.0
        if delta_hours >= min_gap_hours:
            gaps.append((prev_ts, curr_ts, round(delta_hours, 2)))
    return gaps
