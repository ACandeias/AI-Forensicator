"""Browser history collectors: Chrome, Safari, Arc."""

import os
import sqlite3
from typing import List, Optional

from collectors.base import AbstractCollector
from config import AI_URL_PATTERNS, ARTIFACT_PATHS
from schema import AIArtifact


def _build_url_or_clause(column: str, patterns: List[str]) -> str:
    """Build a SQL OR clause matching a column against AI_URL_PATTERNS."""
    clauses = ["{} LIKE ?".format(column) for _ in patterns]
    return "(" + " OR ".join(clauses) + ")"


class ChromeCollector(AbstractCollector):
    """Collect AI-related browsing history from Google Chrome."""

    @property
    def name(self) -> str:
        return "chrome"

    def _history_path(self) -> str:
        return os.path.join(ARTIFACT_PATHS["chrome"], "Default", "History")

    def detect(self) -> bool:
        return os.path.isfile(self._history_path())

    def collect(self) -> List[AIArtifact]:
        db_path = self._history_path()
        if not os.path.isfile(db_path):
            return []

        url_filter = _build_url_or_clause("u.url", AI_URL_PATTERNS)
        query = (
            "SELECT u.url, u.title, v.visit_time, v.visit_duration "
            "FROM urls u JOIN visits v ON u.id = v.url "
            "WHERE " + url_filter + " "
            "ORDER BY v.visit_time DESC"
        )

        rows = self._safe_sqlite_read(db_path, query, tuple(AI_URL_PATTERNS))
        artifacts = []  # type: List[AIArtifact]

        for row in rows:
            url = row.get("url", "")
            title = row.get("title", "")
            visit_time = row.get("visit_time")
            visit_duration = row.get("visit_duration", 0)

            ts = self._parse_chrome_timestamp(visit_time)
            preview = self._content_preview("{} - {}".format(title, url))

            metadata = {
                "url": url,
                "title": title,
                "visit_duration_us": visit_duration,
            }

            artifacts.append(self._make_artifact(
                artifact_type="browser_history",
                timestamp=ts,
                file_path=db_path,
                content_preview=preview,
                metadata=metadata,
            ))

        return artifacts


class SafariCollector(AbstractCollector):
    """Collect AI-related browsing history from Safari."""

    @property
    def name(self) -> str:
        return "safari"

    def _history_path(self) -> str:
        return ARTIFACT_PATHS["safari_history"]

    def detect(self) -> bool:
        return os.path.isfile(self._history_path())

    def collect(self) -> List[AIArtifact]:
        db_path = self._history_path()
        if not os.path.isfile(db_path):
            return []

        url_filter = _build_url_or_clause("hi.url", AI_URL_PATTERNS)
        query = (
            "SELECT hi.url, hv.title, hv.visit_time "
            "FROM history_items hi "
            "JOIN history_visits hv ON hi.id = hv.history_item "
            "WHERE " + url_filter + " "
            "ORDER BY hv.visit_time DESC"
        )

        # Safari's History.db may be protected by TCC (Full Disk Access).
        # We cannot use _safe_sqlite_read here because we need to catch
        # DatabaseError specifically and provide a meaningful message.
        artifacts = []  # type: List[AIArtifact]
        uri = "file:{}?immutable=1".format(db_path)

        try:
            conn = sqlite3.connect(uri, uri=True)
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(query, tuple(AI_URL_PATTERNS))
            rows = [dict(r) for r in cursor.fetchall()]
            conn.close()
        except sqlite3.DatabaseError:
            # TCC denial: macOS blocks access without Full Disk Access
            artifacts.append(self._make_artifact(
                artifact_type="browser_history",
                file_path=db_path,
                content_preview=(
                    "Safari history inaccessible. Grant Full Disk Access "
                    "to Terminal/IDE in System Settings > Privacy & Security."
                ),
                metadata={"error": "TCC_denied", "requires": "Full Disk Access"},
            ))
            return artifacts
        except sqlite3.OperationalError:
            return []

        for row in rows:
            url = row.get("url", "")
            title = row.get("title", "")
            visit_time = row.get("visit_time")

            # Safari uses Cocoa epoch (seconds since 2001-01-01)
            ts = self._parse_timestamp_ms(visit_time) if visit_time else None

            preview = self._content_preview("{} - {}".format(title, url))

            metadata = {
                "url": url,
                "title": title,
            }

            artifacts.append(self._make_artifact(
                artifact_type="browser_history",
                timestamp=ts,
                file_path=db_path,
                content_preview=preview,
                metadata=metadata,
            ))

        return artifacts


class ArcCollector(AbstractCollector):
    """Collect AI-related browsing history from Arc browser."""

    @property
    def name(self) -> str:
        return "arc"

    def _find_history_db(self) -> Optional[str]:
        """Search for Chromium-style History file in Arc User Data/*/."""
        arc_base = ARTIFACT_PATHS["arc"]
        user_data = os.path.join(arc_base, "User Data")
        if not os.path.isdir(user_data):
            return None

        # Check each profile directory for a History file
        try:
            for entry in os.listdir(user_data):
                profile_dir = os.path.join(user_data, entry)
                if not os.path.isdir(profile_dir):
                    continue
                history_file = os.path.join(profile_dir, "History")
                if os.path.isfile(history_file):
                    return history_file
        except OSError:
            pass

        return None

    def detect(self) -> bool:
        return self._find_history_db() is not None

    def collect(self) -> List[AIArtifact]:
        db_path = self._find_history_db()
        if db_path is None:
            return []

        url_filter = _build_url_or_clause("u.url", AI_URL_PATTERNS)
        query = (
            "SELECT u.url, u.title, v.visit_time, v.visit_duration "
            "FROM urls u JOIN visits v ON u.id = v.url "
            "WHERE " + url_filter + " "
            "ORDER BY v.visit_time DESC"
        )

        rows = self._safe_sqlite_read(db_path, query, tuple(AI_URL_PATTERNS))
        artifacts = []  # type: List[AIArtifact]

        for row in rows:
            url = row.get("url", "")
            title = row.get("title", "")
            visit_time = row.get("visit_time")
            visit_duration = row.get("visit_duration", 0)

            ts = self._parse_chrome_timestamp(visit_time)
            preview = self._content_preview("{} - {}".format(title, url))

            metadata = {
                "url": url,
                "title": title,
                "visit_duration_us": visit_duration,
            }

            artifacts.append(self._make_artifact(
                artifact_type="browser_history",
                timestamp=ts,
                file_path=db_path,
                content_preview=preview,
                metadata=metadata,
            ))

        return artifacts
