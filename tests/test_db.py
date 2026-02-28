"""Tests for db.py: database operations with a temporary database."""

import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
import config
import db
from schema import AIArtifact, CollectionRun


@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    """Redirect the database to a temp directory for every test."""
    db_dir = str(tmp_path / "aift_test")
    db_path = os.path.join(db_dir, "aift_test.db")
    monkeypatch.setattr(config, "DB_DIR", db_dir)
    monkeypatch.setattr(config, "DB_PATH", db_path)
    # Also patch db module's imported references
    monkeypatch.setattr(db, "DB_DIR", db_dir)
    monkeypatch.setattr(db, "DB_PATH", db_path)
    return db_path


class TestEnsureDb:
    """Tests for ensure_db."""

    def test_creates_tables(self, temp_db):
        """ensure_db should create the artifacts and collection_runs tables."""
        path = db.ensure_db()
        assert os.path.exists(path)

        conn = sqlite3.connect(path)
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        conn.close()

        table_names = [t[0] for t in tables]
        assert "artifacts" in table_names
        assert "collection_runs" in table_names

    def test_idempotent(self, temp_db):
        """Calling ensure_db twice should not raise."""
        db.ensure_db()
        db.ensure_db()  # Should not raise


class TestInsertAndQuery:
    """Tests for insert_artifact and query_artifacts."""

    def test_insert_and_query(self, temp_db):
        """Insert an artifact and query it back."""
        db.ensure_db()
        artifact = AIArtifact(
            source_tool="test_tool",
            artifact_type="test_type",
            content_preview="Hello world",
            timestamp="2024-01-15T10:30:00+00:00",
        )
        db.insert_artifact(artifact)

        results = db.query_artifacts(source_tool="test_tool")
        assert len(results) == 1
        assert results[0].id == artifact.id
        assert results[0].source_tool == "test_tool"
        assert results[0].content_preview == "Hello world"

    def test_query_with_filters(self, temp_db):
        """Query should respect source_tool and artifact_type filters."""
        db.ensure_db()

        a1 = AIArtifact(source_tool="tool_a", artifact_type="chat")
        a2 = AIArtifact(source_tool="tool_b", artifact_type="file")
        a3 = AIArtifact(source_tool="tool_a", artifact_type="file")
        db.insert_artifact(a1)
        db.insert_artifact(a2)
        db.insert_artifact(a3)

        # Filter by source_tool
        results = db.query_artifacts(source_tool="tool_a")
        assert len(results) == 2

        # Filter by artifact_type
        results = db.query_artifacts(artifact_type="file")
        assert len(results) == 2

        # Combined filter
        results = db.query_artifacts(source_tool="tool_a", artifact_type="file")
        assert len(results) == 1
        assert results[0].id == a3.id


class TestInsertBatch:
    """Tests for insert_artifacts_batch."""

    def test_batch_insert(self, temp_db):
        """Batch insert should insert all artifacts."""
        db.ensure_db()
        artifacts = [
            AIArtifact(source_tool="batch", artifact_type="type_{}".format(i))
            for i in range(10)
        ]
        count = db.insert_artifacts_batch(artifacts)
        assert count == 10

        results = db.query_artifacts(source_tool="batch")
        assert len(results) == 10

    def test_batch_empty(self, temp_db):
        """Batch insert with empty list should return 0."""
        db.ensure_db()
        count = db.insert_artifacts_batch([])
        assert count == 0


class TestSearchArtifacts:
    """Tests for search_artifacts."""

    def test_search_by_content(self, temp_db):
        """search_artifacts should match content_preview."""
        db.ensure_db()
        a = AIArtifact(
            source_tool="searchtest",
            artifact_type="chat",
            content_preview="The quick brown fox jumps over the lazy dog",
        )
        db.insert_artifact(a)

        results = db.search_artifacts("brown fox")
        assert len(results) == 1
        assert results[0].id == a.id

    def test_search_by_file_path(self, temp_db):
        """search_artifacts should match file_path."""
        db.ensure_db()
        a = AIArtifact(
            source_tool="pathtest",
            artifact_type="file",
            file_path="/home/user/.claude/config.json",
        )
        db.insert_artifact(a)

        results = db.search_artifacts("claude/config")
        assert len(results) == 1

    def test_search_no_results(self, temp_db):
        """search_artifacts should return empty list when nothing matches."""
        db.ensure_db()
        results = db.search_artifacts("nonexistent_query_xyz")
        assert results == []


class TestGetStats:
    """Tests for get_stats."""

    def test_stats_structure(self, temp_db):
        """get_stats should return the expected keys."""
        db.ensure_db()
        stats = db.get_stats()

        assert "total_artifacts" in stats
        assert "by_source" in stats
        assert "by_type" in stats
        assert "by_model" in stats
        assert "date_range" in stats
        assert "total_token_estimate" in stats
        assert "collection_runs" in stats

    def test_stats_with_data(self, temp_db):
        """get_stats should reflect inserted data."""
        db.ensure_db()

        artifacts = [
            AIArtifact(
                source_tool="tool_a", artifact_type="chat",
                model_identified="gpt-4", token_estimate=100,
                timestamp="2024-01-15T10:00:00+00:00",
            ),
            AIArtifact(
                source_tool="tool_a", artifact_type="file",
                token_estimate=200,
                timestamp="2024-01-16T10:00:00+00:00",
            ),
            AIArtifact(
                source_tool="tool_b", artifact_type="chat",
                model_identified="claude-3-opus",
                timestamp="2024-01-17T10:00:00+00:00",
            ),
        ]
        db.insert_artifacts_batch(artifacts)

        stats = db.get_stats()
        assert stats["total_artifacts"] == 3
        assert stats["total_token_estimate"] == 300

        source_names = [s[0] for s in stats["by_source"]]
        assert "tool_a" in source_names
        assert "tool_b" in source_names

        model_names = [m[0] for m in stats["by_model"]]
        assert "gpt-4" in model_names
        assert "claude-3-opus" in model_names


class TestWALMode:
    """Tests for WAL journal mode."""

    def test_wal_mode_is_set(self, temp_db):
        """The database should use WAL journal mode."""
        db.ensure_db()
        conn = db._get_connection()
        try:
            mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
            assert mode == "wal"
        finally:
            conn.close()


class TestCollectionRuns:
    """Tests for collection run operations."""

    def test_insert_and_get_runs(self, temp_db):
        """insert_run and get_collection_runs should work together."""
        db.ensure_db()
        run = CollectionRun(
            total_artifacts=42,
            hostname="testhost",
            username="testuser",
        )
        db.insert_run(run)

        runs = db.get_collection_runs()
        assert len(runs) == 1
        assert runs[0]["total_artifacts"] == 42
        assert runs[0]["hostname"] == "testhost"
