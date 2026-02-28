"""Notion artifact collector."""

import json
import os
import re
from typing import Any, Dict, List

from collectors.base import AbstractCollector
from collectors.mixins import ElectronAppMixin
from config import HOME
from normalizer import sanitize_content
from schema import AIArtifact


class NotionCollector(ElectronAppMixin, AbstractCollector):
    """Collect artifacts from the Notion desktop application.

    Artifact root: ~/Library/Application Support/Notion/
    Collects SQLite cache databases (table listings), Electron storage,
    and preference files.
    """

    def __init__(self) -> None:
        super().__init__()
        self._root = os.path.join(
            HOME, "Library", "Application Support", "Notion",
        )

    @property
    def name(self) -> str:
        return "notion"

    def detect(self) -> bool:
        return os.path.isdir(self._root)

    def collect(self) -> List[AIArtifact]:
        if not os.path.isdir(self._root):
            return []

        artifacts = []  # type: List[AIArtifact]
        artifacts.extend(self._collect_sqlite_caches())
        artifacts.extend(self._collect_electron_preferences(self._root))
        artifacts.extend(self._collect_electron_local_storage(self._root))
        artifacts.extend(self._collect_electron_session_storage(self._root))
        artifacts.extend(self._collect_electron_indexed_db(self._root))
        return artifacts

    # ------------------------------------------------------------------
    # 1. SQLite cache databases
    # ------------------------------------------------------------------
    def _collect_sqlite_caches(self) -> List[AIArtifact]:
        """Find *.db files and list their tables using _safe_sqlite_read.
        Artifact type: sqlite_data."""
        results = []  # type: List[AIArtifact]

        for dirpath, _dirnames, filenames in os.walk(self._root):
            if os.path.islink(dirpath):
                continue
            for fname in filenames:
                if not fname.endswith(".db"):
                    continue
                fpath = os.path.join(dirpath, fname)
                if os.path.islink(fpath) or not os.path.isfile(fpath):
                    continue
                if self._is_credential_file(fpath):
                    continue

                fmeta = self._file_metadata(fpath)
                file_hash = self._hash_file(fpath)

                # List tables in this database
                tables = self._safe_sqlite_read(
                    fpath,
                    "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name",
                )
                table_names = [t.get("name", "") for t in tables]

                # Get row counts for each table
                table_info = {}  # type: Dict[str, int]
                for tname in table_names:
                    if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', tname):
                        continue
                    rows = self._safe_sqlite_read(
                        fpath,
                        "SELECT COUNT(*) as cnt FROM \"{}\"".format(tname),
                    )
                    if rows:
                        table_info[tname] = rows[0].get("cnt", 0)

                results.append(self._make_artifact(
                    artifact_type="sqlite_data",
                    file_path=fpath,
                    file_hash_sha256=file_hash,
                    file_size_bytes=fmeta.get("file_size_bytes"),
                    file_modified=fmeta.get("file_modified"),
                    file_created=fmeta.get("file_created"),
                    content_preview="Notion cache DB {}: {} tables, {} total rows".format(
                        fname, len(table_names), sum(table_info.values()),
                    ),
                    metadata={
                        "database_name": fname,
                        "tables": table_names,
                        "table_row_counts": table_info,
                    },
                ))

        return results
