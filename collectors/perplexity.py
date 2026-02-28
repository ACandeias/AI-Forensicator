"""Collector for Perplexity AI desktop application artifacts.

Paths:
  - ~/Library/Application Support/Perplexity/
  - ~/Library/Containers/ai.perplexity.mac/  (sandbox variant)

Perplexity is an Electron app; we use ElectronAppMixin to extract
LevelDB/IndexedDB data, session storage, and preferences.
"""

import json
import os
from typing import Any, Dict, List, Optional

from collectors.base import AbstractCollector
from collectors.mixins import ElectronAppMixin
from config import ARTIFACT_PATHS, HOME
from normalizer import sanitize_content


class PerplexityCollector(ElectronAppMixin, AbstractCollector):
    """Collect artifacts from the Perplexity AI desktop application.

    Artifact roots:
      ~/Library/Application Support/Perplexity/
      ~/Library/Containers/ai.perplexity.mac/
    Contains Electron LevelDB/IndexedDB data, session storage,
    local storage, and preferences.
    """

    def __init__(self) -> None:
        super().__init__()
        self._root = ARTIFACT_PATHS.get(
            "perplexity",
            os.path.join(HOME, "Library", "Application Support", "Perplexity"),
        )
        self._container_root = os.path.join(
            HOME, "Library", "Containers", "ai.perplexity.mac",
        )

    @property
    def name(self) -> str:
        return "perplexity"

    def detect(self) -> bool:
        return os.path.isdir(self._root) or os.path.isdir(self._container_root)

    def collect(self) -> List:
        artifacts = []  # type: List[Any]
        for app_root in self._get_app_roots():
            artifacts.extend(self._collect_from_app_root(app_root))
        return artifacts

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    def _get_app_roots(self) -> List[str]:
        """Return all valid Perplexity app data directories."""
        roots = []  # type: List[str]

        if os.path.isdir(self._root):
            roots.append(self._root)

        if os.path.isdir(self._container_root):
            # The container may have the actual data in a Data subdirectory
            data_subdir = os.path.join(
                self._container_root, "Data", "Library",
                "Application Support", "Perplexity",
            )
            if os.path.isdir(data_subdir):
                roots.append(data_subdir)
            elif self._container_root not in roots:
                roots.append(self._container_root)

        return roots

    def _collect_from_app_root(self, app_root: str) -> List:
        """Collect all Electron artifacts from a single app root."""
        results = []  # type: List[Any]
        results.extend(self._collect_electron_indexed_db(app_root))
        results.extend(self._collect_electron_session_storage(app_root))
        results.extend(self._collect_electron_local_storage(app_root))
        results.extend(self._collect_electron_preferences(app_root))
        results.extend(self._collect_json_configs(app_root))
        return results

    # ------------------------------------------------------------------
    # Additional JSON config collection
    # ------------------------------------------------------------------
    def _collect_json_configs(self, app_root: str) -> List:
        """Collect any JSON configuration files in the app root.
        Artifact type: config."""
        results = []  # type: List[Any]

        try:
            entries = os.listdir(app_root)
        except OSError:
            return results

        for fname in entries:
            if not fname.endswith(".json"):
                continue
            # Skip Preferences (handled by ElectronAppMixin)
            if fname == "Preferences":
                continue
            fpath = os.path.join(app_root, fname)
            if os.path.islink(fpath) or not os.path.isfile(fpath):
                continue
            if self._is_credential_file(fpath):
                continue

            data = self._safe_read_json(fpath)
            if data is None:
                continue

            fmeta = self._file_metadata(fpath)
            file_hash = self._hash_file(fpath)
            sanitized = sanitize_content(json.dumps(data))

            results.append(self._make_artifact(
                artifact_type="config",
                file_path=fpath,
                file_hash_sha256=file_hash,
                file_size_bytes=fmeta.get("file_size_bytes"),
                file_modified=fmeta.get("file_modified"),
                file_created=fmeta.get("file_created"),
                content_preview=self._content_preview(sanitized),
                raw_data=sanitized if len(sanitized) < 50000 else None,
                metadata={
                    "filename": fname,
                    "app_root": app_root,
                },
            ))

        return results
