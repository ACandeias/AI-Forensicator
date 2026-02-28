"""Tests for schema.py: AIArtifact and CollectionRun dataclasses."""

import sys
import os
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from schema import AIArtifact, CollectionRun


class TestAIArtifact:
    """Tests for the AIArtifact dataclass."""

    def test_creation_with_defaults(self):
        """AIArtifact should auto-generate id (UUID) and collection_timestamp."""
        artifact = AIArtifact(source_tool="test_tool", artifact_type="test_type")

        # id should be a valid UUID string
        parsed = uuid.UUID(artifact.id)
        assert str(parsed) == artifact.id

        # collection_timestamp should be set (ISO-8601 string)
        assert artifact.collection_timestamp is not None
        assert "T" in artifact.collection_timestamp

        # Required fields
        assert artifact.source_tool == "test_tool"
        assert artifact.artifact_type == "test_type"

        # Optional fields default to None
        assert artifact.timestamp is None
        assert artifact.file_path is None
        assert artifact.file_hash_sha256 is None
        assert artifact.file_size_bytes is None
        assert artifact.file_modified is None
        assert artifact.file_created is None
        assert artifact.user is None
        assert artifact.hostname is None
        assert artifact.content_preview is None
        assert artifact.raw_data is None
        assert artifact.model_identified is None
        assert artifact.conversation_id is None
        assert artifact.message_role is None
        assert artifact.token_estimate is None
        assert artifact.metadata is None

    def test_to_dict_returns_all_fields(self):
        """to_dict() should return a dict with all 19 fields."""
        artifact = AIArtifact(source_tool="test", artifact_type="type")
        d = artifact.to_dict()

        expected_fields = {
            "id", "source_tool", "artifact_type", "timestamp", "file_path",
            "file_hash_sha256", "file_size_bytes", "file_modified", "file_created",
            "user", "hostname", "content_preview", "raw_data", "model_identified",
            "conversation_id", "message_role", "token_estimate", "metadata",
            "collection_timestamp",
        }

        assert isinstance(d, dict)
        assert set(d.keys()) == expected_fields
        assert len(d) == 19

    def test_to_dict_preserves_values(self):
        """to_dict() should preserve all set values."""
        artifact = AIArtifact(
            source_tool="chatgpt",
            artifact_type="conversation",
            user="testuser",
            model_identified="gpt-4",
            token_estimate=1234,
        )
        d = artifact.to_dict()
        assert d["source_tool"] == "chatgpt"
        assert d["artifact_type"] == "conversation"
        assert d["user"] == "testuser"
        assert d["model_identified"] == "gpt-4"
        assert d["token_estimate"] == 1234

    def test_unique_ids(self):
        """Each AIArtifact should get a unique id."""
        a1 = AIArtifact(source_tool="a", artifact_type="b")
        a2 = AIArtifact(source_tool="a", artifact_type="b")
        assert a1.id != a2.id


class TestCollectionRun:
    """Tests for the CollectionRun dataclass."""

    def test_creation_with_defaults(self):
        """CollectionRun should auto-generate id and start_time."""
        run = CollectionRun()

        # id should be a valid UUID string
        parsed = uuid.UUID(run.id)
        assert str(parsed) == run.id

        # start_time should be set
        assert run.start_time is not None
        assert "T" in run.start_time

        # Defaults
        assert run.end_time is None
        assert run.collectors_run is None
        assert run.total_artifacts == 0
        assert run.errors is None
        assert run.hostname is None
        assert run.username is None

    def test_to_dict(self):
        """CollectionRun.to_dict() should return all 8 fields."""
        run = CollectionRun()
        d = run.to_dict()

        expected_fields = {
            "id", "start_time", "end_time", "collectors_run",
            "total_artifacts", "errors", "hostname", "username",
        }
        assert set(d.keys()) == expected_fields
        assert len(d) == 8
