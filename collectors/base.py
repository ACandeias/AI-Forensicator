"""Abstract base collector with shared helper methods."""

import getpass
import hashlib
import json
import os
import platform
import re
import sqlite3
import urllib.parse
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Dict, Generator, List, Optional, Tuple

from config import (
    CONTENT_PREVIEW_MAX, CREDENTIAL_FILES, CREDENTIAL_PATTERNS,
    MAX_FILE_READ_BYTES,
)
from normalizer import (
    normalize_timestamp, sanitize_content, content_preview,
    estimate_model_from_content, CHROME_EPOCH_OFFSET,
)
from schema import AIArtifact


class AbstractCollector(ABC):
    """Base class for all artifact collectors."""

    def __init__(self) -> None:
        self._user = getpass.getuser()
        self._hostname = platform.node()

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable collector name."""
        ...

    @abstractmethod
    def detect(self) -> bool:
        """Check if this tool's artifacts exist on the system."""
        ...

    @abstractmethod
    def collect(self) -> List[AIArtifact]:
        """Collect all artifacts. Returns list of AIArtifact."""
        ...

    # --- File helpers ---

    def _hash_file(self, path: str, max_bytes: int = MAX_FILE_READ_BYTES) -> Optional[str]:
        """SHA-256 hash of a file, read in 64KB chunks. Skips files over max_bytes."""
        try:
            if os.path.getsize(path) > max_bytes:
                return None
            h = hashlib.sha256()
            with open(path, "rb") as f:
                while True:
                    chunk = f.read(65536)
                    if not chunk:
                        break
                    h.update(chunk)
            return h.hexdigest()
        except (OSError, IOError):
            return None

    def _safe_read_text(self, path: str, max_bytes: int = MAX_FILE_READ_BYTES) -> Optional[str]:
        """Read a text file safely with size guard and encoding fallback."""
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                data = f.read(max_bytes + 1)
                if len(data) > max_bytes:
                    return None
                return data
        except (OSError, IOError):
            return None

    def _safe_read_json(self, path: str) -> Optional[Any]:
        """Read and parse a JSON file safely."""
        text = self._safe_read_text(path)
        if text is None:
            return None
        try:
            return json.loads(text)
        except (json.JSONDecodeError, ValueError):
            return None

    def _safe_read_jsonl(self, path: str) -> Generator[Dict[str, Any], None, None]:
        """Yield parsed JSON objects from a JSONL file, line by line."""
        try:
            fsize = os.path.getsize(path)
            if fsize > MAX_FILE_READ_BYTES:
                return
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        yield json.loads(line)
                    except (json.JSONDecodeError, ValueError):
                        continue
        except (OSError, IOError):
            return

    # --- Content helpers ---

    def _estimate_tokens(self, text: str) -> int:
        """Rough token estimate: len // 4."""
        if not text:
            return 0
        return len(text) // 4

    def _content_preview(self, text: str) -> str:
        """Truncate and sanitize text for preview."""
        return content_preview(text, CONTENT_PREVIEW_MAX)

    # --- File metadata ---

    def _file_metadata(self, path: str) -> Dict[str, Any]:
        """Get file size, mtime, and birthtime."""
        try:
            st = os.stat(path)
            result = {
                "file_size_bytes": st.st_size,
                "file_modified": normalize_timestamp(st.st_mtime),
            }
            # macOS birthtime
            birthtime = getattr(st, "st_birthtime", None)
            if birthtime:
                result["file_created"] = normalize_timestamp(birthtime)
            else:
                result["file_created"] = None
            return result
        except (OSError, IOError):
            return {"file_size_bytes": None, "file_modified": None, "file_created": None}

    # --- Timestamp helpers ---

    def _parse_timestamp_ms(self, ms: Any) -> Optional[str]:
        """Parse millisecond epoch timestamp to ISO string."""
        if ms is None:
            return None
        try:
            return normalize_timestamp(float(ms))
        except (ValueError, TypeError):
            return None

    def _parse_chrome_timestamp(self, ts: Any) -> Optional[str]:
        """Parse Chrome/WebKit microsecond timestamp (since 1601-01-01)."""
        if ts is None:
            return None
        try:
            v = float(ts)
            epoch_seconds = (v / 1_000_000) - CHROME_EPOCH_OFFSET
            dt = datetime.fromtimestamp(epoch_seconds, tz=timezone.utc)
            return dt.isoformat()
        except (OSError, OverflowError, ValueError):
            return None

    # --- Security helpers ---

    def _is_credential_file(self, path: str) -> bool:
        """Check if a file is a known credential file."""
        basename = os.path.basename(path)
        return basename in CREDENTIAL_FILES

    def _contains_credentials(self, text: str) -> bool:
        """Check if text contains credential patterns."""
        if not text:
            return False
        for pattern in CREDENTIAL_PATTERNS:
            if pattern.search(text):
                return True
        return False

    # --- Artifact factory ---

    def _make_artifact(self, **kwargs: Any) -> AIArtifact:
        """Create an AIArtifact with common fields pre-filled."""
        kwargs.setdefault("source_tool", self.name)
        kwargs.setdefault("user", self._user)
        kwargs.setdefault("hostname", self._hostname)
        if "metadata" in kwargs and isinstance(kwargs["metadata"], dict):
            kwargs["metadata"] = json.dumps(kwargs["metadata"])
        return AIArtifact(**kwargs)

    # --- SQLite helper ---

    def _safe_sqlite_read(
        self, db_path: str, query: str, params: Optional[Tuple] = None
    ) -> List[Dict[str, Any]]:
        """Open a SQLite DB in immutable mode and run a read query."""
        import logging
        results = []
        uri = "file:{}?immutable=1".format(urllib.parse.quote(db_path))
        try:
            conn = sqlite3.connect(uri, uri=True)
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(query, params or ())
            results = [dict(row) for row in cursor.fetchall()]
            conn.close()
        except (sqlite3.OperationalError, sqlite3.DatabaseError) as exc:
            logging.getLogger("aift").debug(
                "SQLite read failed for %s: %s", db_path, exc
            )
        return results

    # --- LevelDB string extraction ---

    def _extract_leveldb_strings(
        self, directory: str, min_length: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Extract printable strings from LevelDB files (.log, .ldb).
        Returns list of dicts with 'source_file', 'content', and optionally 'json_data'.
        """
        results = []
        if not os.path.isdir(directory):
            return results

        pattern = re.compile(b'([\x20-\x7e]{' + str(min_length).encode() + b',})')

        for fname in os.listdir(directory):
            if not (fname.endswith(".log") or fname.endswith(".ldb")):
                continue
            fpath = os.path.join(directory, fname)
            if os.path.islink(fpath):
                continue
            try:
                fsize = os.path.getsize(fpath)
                if fsize > MAX_FILE_READ_BYTES:
                    continue
                with open(fpath, "rb") as f:
                    data = f.read()
            except (OSError, IOError):
                continue

            for match in pattern.finditer(data):
                text = match.group(1).decode("ascii", errors="replace")
                # Skip credential content
                if self._contains_credentials(text):
                    continue
                entry = {"source_file": fname, "content": text}  # type: Dict[str, Any]
                # Try parsing as JSON
                try:
                    parsed = json.loads(text)
                    entry["json_data"] = parsed
                except (json.JSONDecodeError, ValueError):
                    pass
                results.append(entry)

        return results
