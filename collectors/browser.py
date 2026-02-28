"""Browser history collectors: Chrome, Safari, Arc."""

import os
import sqlite3
from typing import List, Optional

from collectors.base import AbstractCollector
from collectors.mixins import ChromiumHistoryMixin, _build_url_or_clause
from config import AI_URL_PATTERNS, ARTIFACT_PATHS
from schema import AIArtifact


class ChromeCollector(ChromiumHistoryMixin, AbstractCollector):
    """Collect AI-related browsing history from Google Chrome."""

    @property
    def name(self) -> str:
        return "chrome"

    def _history_path(self) -> str:
        return os.path.join(ARTIFACT_PATHS["chrome"], "Default", "History")

    def detect(self) -> bool:
        return os.path.isfile(self._history_path())

    def collect(self) -> List[AIArtifact]:
        return self._collect_chromium_history(self._history_path())


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
        import urllib.parse
        uri = "file:{}?immutable=1".format(urllib.parse.quote(db_path))

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


class ArcCollector(ChromiumHistoryMixin, AbstractCollector):
    """Collect AI-related browsing history from Arc browser."""

    @property
    def name(self) -> str:
        return "arc"

    def _find_history_db(self) -> Optional[str]:
        """Search for Chromium-style History file in Arc User Data/*/."""
        return self._find_chromium_history_db(ARTIFACT_PATHS["arc"])

    def detect(self) -> bool:
        return self._find_history_db() is not None

    def collect(self) -> List[AIArtifact]:
        return self._collect_chromium_history(self._find_history_db())
