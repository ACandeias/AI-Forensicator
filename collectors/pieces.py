"""Pieces artifact collector."""

import json
import os
from typing import Any, Dict, List

from collectors.base import AbstractCollector
from config import HOME
from normalizer import sanitize_content
from schema import AIArtifact


class PiecesCollector(AbstractCollector):
    """Collect artifacts from Pieces for Developers.

    Artifact root: ~/Library/com.pieces.os/
    Collects snippet inventory (metadata), context metadata, and production logs.
    """

    def __init__(self) -> None:
        super().__init__()
        self._root = os.path.join(HOME, "Library", "com.pieces.os")

    @property
    def name(self) -> str:
        return "pieces"

    def detect(self) -> bool:
        return os.path.isdir(self._root)

    def collect(self) -> List[AIArtifact]:
        if not os.path.isdir(self._root):
            return []

        artifacts = []  # type: List[AIArtifact]
        artifacts.extend(self._collect_snippet_inventory())
        artifacts.extend(self._collect_context_metadata())
        artifacts.extend(self._collect_production_logs())
        return artifacts

    # ------------------------------------------------------------------
    # 1. Snippet inventory (metadata only)
    # ------------------------------------------------------------------
    def _collect_snippet_inventory(self) -> List[AIArtifact]:
        """Inventory saved snippets by metadata.
        Artifact type: snippet_inventory."""
        results = []  # type: List[AIArtifact]

        # Look for snippet data in JSON files
        snippet_entries = []  # type: List[Dict[str, Any]]

        for dirpath, _dirnames, filenames in os.walk(self._root):
            if os.path.islink(dirpath):
                continue
            for fname in filenames:
                if not fname.endswith(".json"):
                    continue
                # Look for snippet-related files
                fname_lower = fname.lower()
                if not any(
                    kw in fname_lower
                    for kw in ("snippet", "asset", "piece", "format")
                ):
                    continue

                fpath = os.path.join(dirpath, fname)
                if os.path.islink(fpath) or not os.path.isfile(fpath):
                    continue
                if self._is_credential_file(fpath):
                    continue

                fmeta = self._file_metadata(fpath)
                file_hash = self._hash_file(fpath)

                data = self._safe_read_json(fpath)
                if data is None:
                    continue

                sanitized = sanitize_content(json.dumps(data, default=str))

                entry_count = 0
                if isinstance(data, list):
                    entry_count = len(data)
                elif isinstance(data, dict):
                    entry_count = 1

                snippet_entries.append({
                    "filename": fname,
                    "relative_path": os.path.relpath(fpath, self._root),
                    "entry_count": entry_count,
                    "size_bytes": fmeta.get("file_size_bytes") or 0,
                })

                results.append(self._make_artifact(
                    artifact_type="snippet_inventory",
                    file_path=fpath,
                    file_hash_sha256=file_hash,
                    file_size_bytes=fmeta.get("file_size_bytes"),
                    file_modified=fmeta.get("file_modified"),
                    file_created=fmeta.get("file_created"),
                    content_preview=self._content_preview(sanitized),
                    raw_data=sanitized if len(sanitized) < 50000 else None,
                    metadata={
                        "filename": fname,
                        "entry_count": entry_count,
                    },
                ))

        if snippet_entries and len(snippet_entries) > 1:
            # Add summary artifact
            total_entries = sum(e.get("entry_count", 0) for e in snippet_entries)
            results.insert(0, self._make_artifact(
                artifact_type="snippet_inventory",
                file_path=self._root,
                content_preview="Pieces: {} snippet files, {} total entries".format(
                    len(snippet_entries), total_entries,
                ),
                metadata={
                    "file_count": len(snippet_entries),
                    "total_entries": total_entries,
                    "files": snippet_entries,
                },
            ))

        return results

    # ------------------------------------------------------------------
    # 2. Context metadata
    # ------------------------------------------------------------------
    def _collect_context_metadata(self) -> List[AIArtifact]:
        """Collect context and conversation metadata files.
        Artifact type: context_metadata."""
        results = []  # type: List[AIArtifact]

        for dirpath, _dirnames, filenames in os.walk(self._root):
            if os.path.islink(dirpath):
                continue
            for fname in filenames:
                if not fname.endswith(".json"):
                    continue
                fname_lower = fname.lower()
                if not any(
                    kw in fname_lower
                    for kw in ("context", "conversation", "anchor", "annotation")
                ):
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
                    artifact_type="context_metadata",
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

    # ------------------------------------------------------------------
    # 3. Production logs
    # ------------------------------------------------------------------
    def _collect_production_logs(self) -> List[AIArtifact]:
        """Collect production log files.
        Artifact type: log."""
        results = []  # type: List[AIArtifact]

        for dirpath, _dirnames, filenames in os.walk(self._root):
            if os.path.islink(dirpath):
                continue
            for fname in filenames:
                if not (fname.endswith(".log") or fname.endswith(".txt")):
                    continue
                fname_lower = fname.lower()
                if "log" not in fname_lower and "production" not in fname_lower:
                    continue

                fpath = os.path.join(dirpath, fname)
                if os.path.islink(fpath) or not os.path.isfile(fpath):
                    continue

                fmeta = self._file_metadata(fpath)
                file_hash = self._hash_file(fpath)

                text = self._safe_read_text(fpath)
                if text is None:
                    continue

                sanitized = sanitize_content(text)
                line_count = text.count("\n")

                results.append(self._make_artifact(
                    artifact_type="log",
                    file_path=fpath,
                    file_hash_sha256=file_hash,
                    file_size_bytes=fmeta.get("file_size_bytes"),
                    file_modified=fmeta.get("file_modified"),
                    file_created=fmeta.get("file_created"),
                    content_preview=self._content_preview(sanitized),
                    raw_data=sanitized if len(sanitized) < 50000 else None,
                    metadata={
                        "filename": fname,
                        "line_count": line_count,
                        "relative_path": os.path.relpath(fpath, self._root),
                    },
                ))

        return results
