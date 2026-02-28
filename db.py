"""AIFT database layer: SQLite with WAL mode for artifact storage."""

import json
import os
import sqlite3
from typing import Any, Dict, List, Optional, Tuple

from config import DB_DIR, DB_PATH
from schema import AIArtifact, CollectionRun

# Column order for AIArtifact
ARTIFACT_COLUMNS = [
    "id", "source_tool", "artifact_type", "timestamp", "file_path",
    "file_hash_sha256", "file_size_bytes", "file_modified", "file_created",
    "user", "hostname", "content_preview", "raw_data", "model_identified",
    "conversation_id", "message_role", "token_estimate", "metadata",
    "collection_timestamp",
]

RUN_COLUMNS = [
    "id", "start_time", "end_time", "collectors_run", "total_artifacts",
    "errors", "hostname", "username",
]


def _get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, uri=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn


def ensure_db() -> str:
    """Create DB directory and tables if they don't exist. Returns DB path."""
    os.makedirs(DB_DIR, mode=0o700, exist_ok=True)
    conn = _get_connection()
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS artifacts (
                id TEXT PRIMARY KEY,
                source_tool TEXT NOT NULL,
                artifact_type TEXT NOT NULL,
                timestamp TEXT,
                file_path TEXT,
                file_hash_sha256 TEXT,
                file_size_bytes INTEGER,
                file_modified TEXT,
                file_created TEXT,
                user TEXT,
                hostname TEXT,
                content_preview TEXT,
                raw_data TEXT,
                model_identified TEXT,
                conversation_id TEXT,
                message_role TEXT,
                token_estimate INTEGER,
                metadata TEXT,
                collection_timestamp TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_source_tool ON artifacts(source_tool);
            CREATE INDEX IF NOT EXISTS idx_timestamp ON artifacts(timestamp);
            CREATE INDEX IF NOT EXISTS idx_artifact_type ON artifacts(artifact_type);
            CREATE INDEX IF NOT EXISTS idx_conversation_id ON artifacts(conversation_id);

            CREATE TABLE IF NOT EXISTS collection_runs (
                id TEXT PRIMARY KEY,
                start_time TEXT NOT NULL,
                end_time TEXT,
                collectors_run TEXT,
                total_artifacts INTEGER DEFAULT 0,
                errors TEXT,
                hostname TEXT,
                username TEXT
            );
        """)
        conn.commit()
    finally:
        conn.close()
    return DB_PATH


def insert_artifact(artifact: AIArtifact) -> None:
    """Insert a single artifact."""
    conn = _get_connection()
    try:
        d = artifact.to_dict()
        placeholders = ", ".join(["?"] * len(ARTIFACT_COLUMNS))
        cols = ", ".join(ARTIFACT_COLUMNS)
        values = [d[c] for c in ARTIFACT_COLUMNS]
        conn.execute(
            "INSERT OR REPLACE INTO artifacts ({}) VALUES ({})".format(cols, placeholders),
            values,
        )
        conn.commit()
    finally:
        conn.close()


def insert_artifacts_batch(artifacts: List[AIArtifact]) -> int:
    """Insert multiple artifacts in a single transaction. Returns count inserted."""
    if not artifacts:
        return 0
    conn = _get_connection()
    try:
        placeholders = ", ".join(["?"] * len(ARTIFACT_COLUMNS))
        cols = ", ".join(ARTIFACT_COLUMNS)
        sql = "INSERT OR REPLACE INTO artifacts ({}) VALUES ({})".format(cols, placeholders)
        rows = []
        for a in artifacts:
            d = a.to_dict()
            rows.append([d[c] for c in ARTIFACT_COLUMNS])
        conn.executemany(sql, rows)
        conn.commit()
        return len(rows)
    finally:
        conn.close()


def insert_run(run: CollectionRun) -> None:
    """Insert a collection run record."""
    conn = _get_connection()
    try:
        d = run.to_dict()
        placeholders = ", ".join(["?"] * len(RUN_COLUMNS))
        cols = ", ".join(RUN_COLUMNS)
        values = [d[c] for c in RUN_COLUMNS]
        conn.execute(
            "INSERT OR REPLACE INTO collection_runs ({}) VALUES ({})".format(cols, placeholders),
            values,
        )
        conn.commit()
    finally:
        conn.close()


def _rows_to_artifacts(rows: List[sqlite3.Row]) -> List[AIArtifact]:
    """Convert DB rows to AIArtifact objects."""
    results = []
    for row in rows:
        d = dict(row)
        results.append(AIArtifact(**d))
    return results


def query_artifacts(
    source_tool: Optional[str] = None,
    artifact_type: Optional[str] = None,
    conversation_id: Optional[str] = None,
    model_identified: Optional[str] = None,
    limit: int = 1000,
    offset: int = 0,
) -> List[AIArtifact]:
    """Query artifacts with optional filters."""
    conn = _get_connection()
    try:
        conditions = []  # type: List[str]
        params = []  # type: List[Any]
        if source_tool:
            conditions.append("source_tool = ?")
            params.append(source_tool)
        if artifact_type:
            conditions.append("artifact_type = ?")
            params.append(artifact_type)
        if conversation_id:
            conditions.append("conversation_id = ?")
            params.append(conversation_id)
        if model_identified:
            conditions.append("model_identified = ?")
            params.append(model_identified)

        where = " WHERE " + " AND ".join(conditions) if conditions else ""
        sql = "SELECT * FROM artifacts{} ORDER BY timestamp DESC LIMIT ? OFFSET ?".format(where)
        params.extend([limit, offset])
        rows = conn.execute(sql, params).fetchall()
        return _rows_to_artifacts(rows)
    finally:
        conn.close()


def search_artifacts(query: str, limit: int = 100) -> List[AIArtifact]:
    """Full-text search on content_preview and file_path."""
    conn = _get_connection()
    try:
        pattern = "%{}%".format(query)
        sql = """
            SELECT * FROM artifacts
            WHERE content_preview LIKE ? OR file_path LIKE ? OR raw_data LIKE ?
            ORDER BY timestamp DESC
            LIMIT ?
        """
        rows = conn.execute(sql, [pattern, pattern, pattern, limit]).fetchall()
        return _rows_to_artifacts(rows)
    finally:
        conn.close()


def get_stats() -> Dict[str, Any]:
    """Get summary statistics from the database."""
    conn = _get_connection()
    try:
        total = conn.execute("SELECT COUNT(*) FROM artifacts").fetchone()[0]
        by_source = conn.execute(
            "SELECT source_tool, COUNT(*) as cnt FROM artifacts GROUP BY source_tool ORDER BY cnt DESC"
        ).fetchall()
        by_type = conn.execute(
            "SELECT artifact_type, COUNT(*) as cnt FROM artifacts GROUP BY artifact_type ORDER BY cnt DESC"
        ).fetchall()
        by_model = conn.execute(
            "SELECT model_identified, COUNT(*) as cnt FROM artifacts "
            "WHERE model_identified IS NOT NULL GROUP BY model_identified ORDER BY cnt DESC"
        ).fetchall()
        date_range = conn.execute(
            "SELECT MIN(timestamp), MAX(timestamp) FROM artifacts WHERE timestamp IS NOT NULL"
        ).fetchone()
        total_tokens = conn.execute(
            "SELECT SUM(token_estimate) FROM artifacts WHERE token_estimate IS NOT NULL"
        ).fetchone()[0]
        runs = conn.execute("SELECT COUNT(*) FROM collection_runs").fetchone()[0]
        return {
            "total_artifacts": total,
            "by_source": [(dict(r)["source_tool"], dict(r)["cnt"]) for r in by_source],
            "by_type": [(dict(r)["artifact_type"], dict(r)["cnt"]) for r in by_type],
            "by_model": [(dict(r)["model_identified"], dict(r)["cnt"]) for r in by_model],
            "date_range": (date_range[0], date_range[1]) if date_range else (None, None),
            "total_token_estimate": total_tokens or 0,
            "collection_runs": runs,
        }
    finally:
        conn.close()


def get_timeline(
    start: Optional[str] = None,
    end: Optional[str] = None,
    source_tool: Optional[str] = None,
    limit: int = 5000,
) -> List[AIArtifact]:
    """Get artifacts ordered chronologically for timeline view."""
    conn = _get_connection()
    try:
        conditions = ["timestamp IS NOT NULL"]
        params = []  # type: List[Any]
        if start:
            conditions.append("timestamp >= ?")
            params.append(start)
        if end:
            conditions.append("timestamp <= ?")
            params.append(end)
        if source_tool:
            conditions.append("source_tool = ?")
            params.append(source_tool)
        where = " WHERE " + " AND ".join(conditions)
        sql = "SELECT * FROM artifacts{} ORDER BY timestamp ASC LIMIT ?".format(where)
        params.append(limit)
        rows = conn.execute(sql, params).fetchall()
        return _rows_to_artifacts(rows)
    finally:
        conn.close()


def get_collection_runs(limit: int = 20) -> List[Dict[str, Any]]:
    """Get recent collection runs."""
    conn = _get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM collection_runs ORDER BY start_time DESC LIMIT ?",
            [limit],
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_artifact_count() -> int:
    """Get total artifact count."""
    conn = _get_connection()
    try:
        return conn.execute("SELECT COUNT(*) FROM artifacts").fetchone()[0]
    finally:
        conn.close()
