"""AIFT statistics: summary metrics, model usage, and token estimates."""

import sys
import os
from collections import defaultdict
from typing import Any, Dict, List, Tuple

# Allow imports from the project root.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import db
from schema import AIArtifact


def _all_artifacts() -> List[AIArtifact]:
    """Fetch all artifacts from the database (up to a generous limit)."""
    return db.query_artifacts(limit=100000, offset=0)


# ------------------------------------------------------------------
# Public API
# ------------------------------------------------------------------

def compute_summary_stats() -> Dict[str, Any]:
    """High-level summary of the database contents.

    Returns
    -------
    dict
        Keys: ``total_artifacts``, ``unique_sources``, ``unique_types``,
        ``date_range`` (tuple of earliest/latest ISO timestamps or Nones),
        ``total_tokens``.
    """
    stats = db.get_stats()
    unique_sources = len(stats["by_source"])
    unique_types = len(stats["by_type"])
    return {
        "total_artifacts": stats["total_artifacts"],
        "unique_sources": unique_sources,
        "unique_types": unique_types,
        "date_range": stats["date_range"],
        "total_tokens": stats["total_token_estimate"],
    }


def compute_model_usage() -> List[Tuple[str, int]]:
    """Model usage ranked by artifact count (descending).

    Returns
    -------
    list of (model_name, count)
    """
    stats = db.get_stats()
    return stats["by_model"]


def compute_daily_activity() -> Dict[str, int]:
    """Artifact counts per calendar day.

    Returns
    -------
    dict mapping ``YYYY-MM-DD`` strings to integer counts, sorted
    chronologically.
    """
    artifacts = _all_artifacts()
    counts = defaultdict(int)  # type: Dict[str, int]
    for a in artifacts:
        if a.timestamp:
            day = a.timestamp[:10]
            counts[day] += 1
    # Return sorted by date.
    return dict(sorted(counts.items()))


def compute_tool_distribution() -> List[Tuple[str, int]]:
    """Source-tool distribution ranked by artifact count (descending).

    Returns
    -------
    list of (tool_name, count)
    """
    stats = db.get_stats()
    return stats["by_source"]


def compute_conversation_stats() -> Dict[str, Any]:
    """Conversation-level statistics.

    Returns
    -------
    dict
        Keys: ``total_conversations``, ``avg_messages_per_conversation``,
        ``models_used`` (list of model name strings).
    """
    artifacts = _all_artifacts()

    conversation_counts = defaultdict(int)  # type: Dict[str, int]
    models_seen = set()  # type: set

    for a in artifacts:
        if a.conversation_id:
            conversation_counts[a.conversation_id] += 1
        if a.model_identified:
            models_seen.add(a.model_identified)

    total_conversations = len(conversation_counts)
    if total_conversations > 0:
        avg_messages = sum(conversation_counts.values()) / float(total_conversations)
    else:
        avg_messages = 0.0

    return {
        "total_conversations": total_conversations,
        "avg_messages_per_conversation": round(avg_messages, 2),
        "models_used": sorted(models_seen),
    }


def compute_token_estimates() -> Dict[str, Any]:
    """Token-estimate breakdown.

    Returns
    -------
    dict
        Keys: ``total_tokens``, ``by_source`` (dict mapping source name to
        token sum), ``by_model`` (dict mapping model name to token sum).
    """
    artifacts = _all_artifacts()

    total = 0
    by_source = defaultdict(int)  # type: Dict[str, int]
    by_model = defaultdict(int)   # type: Dict[str, int]

    for a in artifacts:
        tokens = a.token_estimate or 0
        total += tokens
        if tokens > 0:
            by_source[a.source_tool] += tokens
            if a.model_identified:
                by_model[a.model_identified] += tokens

    return {
        "total_tokens": total,
        "by_source": dict(by_source),
        "by_model": dict(by_model),
    }
