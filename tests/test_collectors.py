"""Tests for collector helper methods in collectors.base."""

import hashlib
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from collectors.base import AbstractCollector
from schema import AIArtifact
from normalizer import normalize_timestamp, CHROME_EPOCH_OFFSET
from typing import List


class _DummyCollector(AbstractCollector):
    """Concrete collector for testing base class helpers."""

    @property
    def name(self) -> str:
        return "dummy"

    def detect(self) -> bool:
        return True

    def collect(self) -> List[AIArtifact]:
        return []


@pytest.fixture
def collector():
    """Create a DummyCollector instance."""
    return _DummyCollector()


class TestEstimateTokens:
    """Tests for _estimate_tokens."""

    def test_basic(self, collector):
        assert collector._estimate_tokens("hello world 1234") == len("hello world 1234") // 4

    def test_empty_string(self, collector):
        assert collector._estimate_tokens("") == 0

    def test_none_like(self, collector):
        # Empty string returns 0
        assert collector._estimate_tokens("") == 0

    def test_long_string(self, collector):
        text = "a" * 1000
        assert collector._estimate_tokens(text) == 250


class TestContentPreview:
    """Tests for _content_preview truncation."""

    def test_short_string(self, collector):
        result = collector._content_preview("hello")
        assert result == "hello"

    def test_truncation(self, collector):
        # CONTENT_PREVIEW_MAX is 500
        long_text = "x" * 600
        result = collector._content_preview(long_text)
        assert len(result) == 500
        assert result.endswith("...")


class TestIsCredentialFile:
    """Tests for _is_credential_file."""

    def test_known_credential_files(self, collector):
        assert collector._is_credential_file("/some/path/.env") is True
        assert collector._is_credential_file("/path/to/credentials.json") is True
        assert collector._is_credential_file("/path/.netrc") is True
        assert collector._is_credential_file("/path/token.json") is True

    def test_normal_files(self, collector):
        assert collector._is_credential_file("/path/readme.md") is False
        assert collector._is_credential_file("/path/config.py") is False
        assert collector._is_credential_file("/path/data.json") is False


class TestContainsCredentials:
    """Tests for _contains_credentials."""

    def test_api_key_detected(self, collector):
        text = "my key is sk-abcdefghijklmnopqrstuvwxyz1234"
        assert collector._contains_credentials(text) is True

    def test_github_token_detected(self, collector):
        text = "token: ghp_abcdefghijklmnopqrstuvwxyz1234567890"
        assert collector._contains_credentials(text) is True

    def test_clean_text(self, collector):
        text = "This is just a normal conversation about AI."
        assert collector._contains_credentials(text) is False

    def test_empty_text(self, collector):
        assert collector._contains_credentials("") is False
        assert collector._contains_credentials(None) is False


class TestHashFile:
    """Tests for _hash_file."""

    def test_hash_temp_file(self, collector, tmp_path):
        """_hash_file should return the correct SHA-256 hash."""
        test_file = tmp_path / "test.txt"
        content = b"hello world"
        test_file.write_bytes(content)

        expected = hashlib.sha256(content).hexdigest()
        result = collector._hash_file(str(test_file))
        assert result == expected

    def test_hash_nonexistent_file(self, collector):
        result = collector._hash_file("/nonexistent/file.txt")
        assert result is None


class TestParseChromeTimestamp:
    """Tests for _parse_chrome_timestamp."""

    def test_known_value(self, collector):
        """Chrome timestamp for 2024-01-01 00:00:00 UTC.

        Chrome epoch: 1601-01-01 00:00:00 UTC
        Microseconds from 1601 to 2024-01-01 = (CHROME_EPOCH_OFFSET + 1704067200) * 1_000_000
        """
        # 2024-01-01 00:00:00 UTC in Unix epoch seconds = 1704067200
        chrome_ts = (1704067200 + CHROME_EPOCH_OFFSET) * 1_000_000
        result = collector._parse_chrome_timestamp(chrome_ts)
        assert result is not None
        assert "2024-01-01" in result

    def test_none(self, collector):
        assert collector._parse_chrome_timestamp(None) is None


class TestNormalizeTimestamp:
    """Tests for timestamp normalization via the normalizer module."""

    def test_epoch_seconds(self):
        """Unix epoch seconds (10 digits) should normalize."""
        result = normalize_timestamp(1704067200)  # 2024-01-01 00:00:00 UTC
        assert result is not None
        assert "2024-01-01" in result

    def test_epoch_milliseconds(self):
        """Unix epoch milliseconds (13 digits) should normalize."""
        result = normalize_timestamp(1704067200000)  # 2024-01-01 in ms
        assert result is not None
        assert "2024-01-01" in result

    def test_iso_string(self):
        """ISO-8601 string should pass through."""
        result = normalize_timestamp("2024-01-15T10:30:00+00:00")
        assert result is not None
        assert "2024-01-15" in result

    def test_iso_string_with_z(self):
        """ISO-8601 string with Z suffix should normalize."""
        result = normalize_timestamp("2024-01-15T10:30:00Z")
        assert result is not None
        assert "2024-01-15" in result

    def test_none(self):
        assert normalize_timestamp(None) is None
