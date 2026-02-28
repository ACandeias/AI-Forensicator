"""Grammarly artifact collector."""

import json
import os
from typing import Any, Dict, List

from collectors.base import AbstractCollector
from config import HOME
from normalizer import sanitize_content
from schema import AIArtifact


class GrammarlyCollector(AbstractCollector):
    """Collect artifacts from Grammarly desktop application.

    Artifact root: ~/Library/Application Support/com.grammarly.ProjectLlama/
    Collects launch agent detection, cache info, and preferences.
    """

    def __init__(self) -> None:
        super().__init__()
        self._root = os.path.join(
            HOME, "Library", "Application Support",
            "com.grammarly.ProjectLlama",
        )

    @property
    def name(self) -> str:
        return "grammarly"

    def detect(self) -> bool:
        return os.path.isdir(self._root)

    def collect(self) -> List[AIArtifact]:
        if not os.path.isdir(self._root):
            return []

        artifacts = []  # type: List[AIArtifact]
        artifacts.extend(self._collect_launch_agents())
        artifacts.extend(self._collect_cache_info())
        artifacts.extend(self._collect_preferences())
        return artifacts

    # ------------------------------------------------------------------
    # 1. Launch agent detection
    # ------------------------------------------------------------------
    def _collect_launch_agents(self) -> List[AIArtifact]:
        """Check ~/Library/LaunchAgents/ for Grammarly plist files.
        Artifact type: launch_agent."""
        results = []  # type: List[AIArtifact]

        launch_agents_dir = os.path.join(HOME, "Library", "LaunchAgents")
        if not os.path.isdir(launch_agents_dir):
            return results

        try:
            entries = os.listdir(launch_agents_dir)
        except OSError:
            return results

        grammarly_plists = []  # type: List[str]
        for fname in entries:
            if "grammarly" not in fname.lower():
                continue
            if not fname.endswith(".plist"):
                continue
            fpath = os.path.join(launch_agents_dir, fname)
            if os.path.islink(fpath) or not os.path.isfile(fpath):
                continue
            grammarly_plists.append(fname)

            fmeta = self._file_metadata(fpath)
            file_hash = self._hash_file(fpath)

            # Read plist content for metadata
            text = self._safe_read_text(fpath)
            sanitized = ""
            if text is not None:
                sanitized = sanitize_content(text)

            results.append(self._make_artifact(
                artifact_type="launch_agent",
                file_path=fpath,
                file_hash_sha256=file_hash,
                file_size_bytes=fmeta.get("file_size_bytes"),
                file_modified=fmeta.get("file_modified"),
                file_created=fmeta.get("file_created"),
                content_preview=self._content_preview(sanitized) if sanitized else "Grammarly launch agent: {}".format(fname),
                raw_data=sanitized if sanitized and len(sanitized) < 50000 else None,
                metadata={
                    "filename": fname,
                    "launch_agents_dir": launch_agents_dir,
                },
            ))

        if not grammarly_plists and not results:
            # No launch agents found -- record that fact
            results.append(self._make_artifact(
                artifact_type="launch_agent",
                file_path=launch_agents_dir,
                content_preview="Grammarly: no launch agent plists detected",
                metadata={
                    "grammarly_agents_found": 0,
                },
            ))

        return results

    # ------------------------------------------------------------------
    # 2. Cache info
    # ------------------------------------------------------------------
    def _collect_cache_info(self) -> List[AIArtifact]:
        """Collect cache directory summary info.
        Artifact type: cache_info."""
        results = []  # type: List[AIArtifact]

        cache_dirs = [
            os.path.join(self._root, "Cache"),
            os.path.join(self._root, "GPUCache"),
            os.path.join(self._root, "Code Cache"),
        ]

        for cache_dir in cache_dirs:
            if not os.path.isdir(cache_dir):
                continue

            file_count = 0
            total_size = 0

            try:
                for dirpath, _dirnames, filenames in os.walk(cache_dir):
                    if os.path.islink(dirpath):
                        continue
                    for fname in filenames:
                        fpath = os.path.join(dirpath, fname)
                        if os.path.islink(fpath):
                            continue
                        try:
                            st = os.stat(fpath)
                            file_count += 1
                            total_size += st.st_size
                        except OSError:
                            continue
            except OSError:
                continue

            fmeta = self._file_metadata(cache_dir)
            dirname = os.path.basename(cache_dir)

            results.append(self._make_artifact(
                artifact_type="cache_info",
                file_path=cache_dir,
                file_size_bytes=fmeta.get("file_size_bytes"),
                file_modified=fmeta.get("file_modified"),
                file_created=fmeta.get("file_created"),
                content_preview="Grammarly {}: {} files, {:.1f} MB".format(
                    dirname, file_count,
                    total_size / (1024 * 1024),
                ),
                metadata={
                    "cache_name": dirname,
                    "file_count": file_count,
                    "total_size_bytes": total_size,
                    "total_size_mb": round(total_size / (1024 * 1024), 2),
                },
            ))

        return results

    # ------------------------------------------------------------------
    # 3. Preferences
    # ------------------------------------------------------------------
    def _collect_preferences(self) -> List[AIArtifact]:
        """Collect JSON preference and settings files.
        Artifact type: preferences."""
        results = []  # type: List[AIArtifact]

        for dirpath, _dirnames, filenames in os.walk(self._root):
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
                sanitized = sanitize_content(json.dumps(data, default=str))

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
                        "relative_path": os.path.relpath(fpath, self._root),
                    },
                ))

        return results
