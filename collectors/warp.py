"""Warp terminal artifact collector."""

import json
import os
from typing import Any, Dict, List

from collectors.base import AbstractCollector
from config import HOME
from normalizer import sanitize_content
from schema import AIArtifact


class WarpCollector(AbstractCollector):
    """Collect artifacts from Warp terminal.

    Artifact roots:
      - ~/.warp/
      - ~/Library/Application Support/dev.warp.Warp-Stable/

    Collects launch configs, AI command history (JSON files), and settings.
    """

    def __init__(self) -> None:
        super().__init__()
        self._dot_warp = os.path.join(HOME, ".warp")
        self._app_support = os.path.join(
            HOME, "Library", "Application Support", "dev.warp.Warp-Stable",
        )

    @property
    def name(self) -> str:
        return "warp"

    def detect(self) -> bool:
        return os.path.isdir(self._dot_warp) or os.path.isdir(self._app_support)

    def collect(self) -> List[AIArtifact]:
        artifacts = []  # type: List[AIArtifact]
        artifacts.extend(self._collect_launch_configs())
        artifacts.extend(self._collect_ai_command_history())
        artifacts.extend(self._collect_settings())
        return artifacts

    # ------------------------------------------------------------------
    # 1. Launch configurations
    # ------------------------------------------------------------------
    def _collect_launch_configs(self) -> List[AIArtifact]:
        """Collect launch configuration files from ~/.warp/.
        Artifact type: launch_config."""
        results = []  # type: List[AIArtifact]

        if not os.path.isdir(self._dot_warp):
            return results

        for dirpath, _dirnames, filenames in os.walk(self._dot_warp):
            if os.path.islink(dirpath):
                continue
            for fname in filenames:
                if not (fname.endswith(".yaml") or fname.endswith(".yml")
                        or fname.endswith(".toml")):
                    continue
                fpath = os.path.join(dirpath, fname)
                if os.path.islink(fpath) or not os.path.isfile(fpath):
                    continue
                if self._is_credential_file(fpath):
                    continue

                fmeta = self._file_metadata(fpath)
                file_hash = self._hash_file(fpath)
                text = self._safe_read_text(fpath)
                if text is None:
                    continue

                sanitized = sanitize_content(text)

                results.append(self._make_artifact(
                    artifact_type="launch_config",
                    file_path=fpath,
                    file_hash_sha256=file_hash,
                    file_size_bytes=fmeta.get("file_size_bytes"),
                    file_modified=fmeta.get("file_modified"),
                    file_created=fmeta.get("file_created"),
                    content_preview=self._content_preview(sanitized),
                    raw_data=sanitized if len(sanitized) < 50000 else None,
                    metadata={
                        "filename": fname,
                        "source_dir": "dot_warp",
                    },
                ))

        return results

    # ------------------------------------------------------------------
    # 2. AI command history
    # ------------------------------------------------------------------
    def _collect_ai_command_history(self) -> List[AIArtifact]:
        """Look for JSON files containing AI command history.
        Artifact type: ai_command_history."""
        results = []  # type: List[AIArtifact]

        search_dirs = []  # type: List[str]
        if os.path.isdir(self._dot_warp):
            search_dirs.append(self._dot_warp)
        if os.path.isdir(self._app_support):
            search_dirs.append(self._app_support)

        for search_dir in search_dirs:
            for dirpath, _dirnames, filenames in os.walk(search_dir):
                if os.path.islink(dirpath):
                    continue
                for fname in filenames:
                    if not fname.endswith(".json"):
                        continue
                    fpath = os.path.join(dirpath, fname)
                    if os.path.islink(fpath) or not os.path.isfile(fpath):
                        continue
                    if self._is_credential_file(fpath):
                        continue

                    data = self._safe_read_json(fpath)
                    if data is None:
                        continue

                    fmeta = self._file_metadata(fpath)
                    file_hash = self._hash_file(fpath)
                    sanitized = sanitize_content(
                        json.dumps(data, default=str)
                    )

                    entry_count = 0
                    if isinstance(data, list):
                        entry_count = len(data)
                    elif isinstance(data, dict):
                        entry_count = len(data)

                    # Determine the source directory label
                    if search_dir == self._dot_warp:
                        source_label = "dot_warp"
                    else:
                        source_label = "app_support"

                    results.append(self._make_artifact(
                        artifact_type="ai_command_history",
                        file_path=fpath,
                        file_hash_sha256=file_hash,
                        file_size_bytes=fmeta.get("file_size_bytes"),
                        file_modified=fmeta.get("file_modified"),
                        file_created=fmeta.get("file_created"),
                        content_preview=self._content_preview(sanitized),
                        raw_data=sanitized if len(sanitized) < 50000 else None,
                        metadata={
                            "filename": fname,
                            "source_dir": source_label,
                            "entry_count": entry_count,
                        },
                    ))

        return results

    # ------------------------------------------------------------------
    # 3. Settings
    # ------------------------------------------------------------------
    def _collect_settings(self) -> List[AIArtifact]:
        """Collect Warp settings and preferences files.
        Artifact type: preferences."""
        results = []  # type: List[AIArtifact]

        search_dirs = []  # type: List[str]
        if os.path.isdir(self._dot_warp):
            search_dirs.append(self._dot_warp)
        if os.path.isdir(self._app_support):
            search_dirs.append(self._app_support)

        for search_dir in search_dirs:
            for dirpath, _dirnames, filenames in os.walk(search_dir):
                if os.path.islink(dirpath):
                    continue
                for fname in filenames:
                    fname_lower = fname.lower()
                    # Look for settings/prefs files (skip JSON already
                    # collected in AI history step)
                    if not (fname_lower.endswith(".yaml")
                            or fname_lower.endswith(".yml")
                            or fname_lower.endswith(".toml")):
                        # Also accept specific known settings JSON filenames
                        if fname_lower in ("prefs.json", "settings.json",
                                           "preferences.json", "config.json"):
                            pass
                        else:
                            continue

                    fpath = os.path.join(dirpath, fname)
                    if os.path.islink(fpath) or not os.path.isfile(fpath):
                        continue
                    if self._is_credential_file(fpath):
                        continue

                    fmeta = self._file_metadata(fpath)
                    file_hash = self._hash_file(fpath)

                    if fname.endswith(".json"):
                        data = self._safe_read_json(fpath)
                        if data is None:
                            continue
                        sanitized = sanitize_content(
                            json.dumps(data, default=str)
                        )
                    else:
                        text = self._safe_read_text(fpath)
                        if text is None:
                            continue
                        sanitized = sanitize_content(text)

                    # Determine the source directory label
                    if search_dir == self._dot_warp:
                        source_label = "dot_warp"
                    else:
                        source_label = "app_support"

                    results.append(self._make_artifact(
                        artifact_type="preferences",
                        file_path=fpath,
                        file_hash_sha256=file_hash,
                        file_size_bytes=fmeta.get("file_size_bytes"),
                        file_modified=fmeta.get("file_modified"),
                        file_created=fmeta.get("file_created"),
                        content_preview=self._content_preview(sanitized),
                        raw_data=sanitized if len(sanitized) < 50000 else None,
                        metadata={
                            "filename": fname,
                            "source_dir": source_label,
                        },
                    ))

        return results
