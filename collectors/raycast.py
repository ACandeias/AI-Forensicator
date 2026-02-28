"""Raycast artifact collector."""

import json
import os
from typing import Any, Dict, List

from collectors.base import AbstractCollector
from config import HOME
from normalizer import sanitize_content
from schema import AIArtifact


class RaycastCollector(AbstractCollector):
    """Collect artifacts from Raycast launcher.

    Artifact root: ~/Library/Application Support/com.raycast.macos/
    NOTE: The main Raycast database is encrypted.  We flag its presence
    and collect only extension inventory and preference files.
    """

    def __init__(self) -> None:
        super().__init__()
        self._root = os.path.join(
            HOME, "Library", "Application Support", "com.raycast.macos",
        )

    @property
    def name(self) -> str:
        return "raycast"

    def detect(self) -> bool:
        return os.path.isdir(self._root)

    def collect(self) -> List[AIArtifact]:
        if not os.path.isdir(self._root):
            return []

        artifacts = []  # type: List[AIArtifact]
        artifacts.extend(self._collect_extension_inventory())
        artifacts.extend(self._collect_preferences())
        artifacts.extend(self._flag_encrypted_db())
        return artifacts

    # ------------------------------------------------------------------
    # 1. Extension inventory
    # ------------------------------------------------------------------
    def _collect_extension_inventory(self) -> List[AIArtifact]:
        """Walk for extension manifest/package JSON files.
        Artifact type: extension_inventory."""
        results = []  # type: List[AIArtifact]

        extensions_dir = os.path.join(self._root, "extensions")
        if not os.path.isdir(extensions_dir):
            return results

        ext_entries = []  # type: List[Dict[str, Any]]
        try:
            for entry in os.listdir(extensions_dir):
                ext_path = os.path.join(extensions_dir, entry)
                if not os.path.isdir(ext_path) or os.path.islink(ext_path):
                    continue

                pkg_json = os.path.join(ext_path, "package.json")
                if os.path.isfile(pkg_json):
                    data = self._safe_read_json(pkg_json)
                    if isinstance(data, dict):
                        ext_entries.append({
                            "name": data.get("name", entry),
                            "version": data.get("version", "unknown"),
                            "title": data.get("title", ""),
                            "author": data.get("author", ""),
                            "directory": entry,
                        })
                    else:
                        ext_entries.append({"name": entry, "directory": entry})
                else:
                    ext_entries.append({"name": entry, "directory": entry})
        except OSError:
            return results

        if not ext_entries:
            return results

        fmeta = self._file_metadata(extensions_dir)

        results.append(self._make_artifact(
            artifact_type="extension_inventory",
            file_path=extensions_dir,
            file_size_bytes=fmeta.get("file_size_bytes"),
            file_modified=fmeta.get("file_modified"),
            file_created=fmeta.get("file_created"),
            content_preview="Raycast: {} extensions installed".format(
                len(ext_entries),
            ),
            metadata={
                "extension_count": len(ext_entries),
                "extensions": ext_entries[:100],
            },
        ))

        return results

    # ------------------------------------------------------------------
    # 2. Preferences
    # ------------------------------------------------------------------
    def _collect_preferences(self) -> List[AIArtifact]:
        """Collect JSON preference files.
        Artifact type: preferences."""
        results = []  # type: List[AIArtifact]

        for dirpath, _dirnames, filenames in os.walk(self._root):
            if os.path.islink(dirpath):
                continue
            for fname in filenames:
                if not fname.endswith(".json"):
                    continue
                if "preference" not in fname.lower() and "setting" not in fname.lower():
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
                    },
                ))

        return results

    # ------------------------------------------------------------------
    # 3. Encrypted database flag
    # ------------------------------------------------------------------
    def _flag_encrypted_db(self) -> List[AIArtifact]:
        """Flag the presence of the encrypted Raycast database.
        Artifact type: encrypted_database."""
        results = []  # type: List[AIArtifact]

        # Look for common DB files
        for fname in os.listdir(self._root):
            fpath = os.path.join(self._root, fname)
            if not os.path.isfile(fpath) or os.path.islink(fpath):
                continue
            if not (fname.endswith(".db") or fname.endswith(".sqlite") or fname.endswith(".realm")):
                continue

            fmeta = self._file_metadata(fpath)
            file_hash = self._hash_file(fpath)

            results.append(self._make_artifact(
                artifact_type="encrypted_database",
                file_path=fpath,
                file_hash_sha256=file_hash,
                file_size_bytes=fmeta.get("file_size_bytes"),
                file_modified=fmeta.get("file_modified"),
                file_created=fmeta.get("file_created"),
                content_preview="Raycast encrypted database: {} ({} bytes)".format(
                    fname, fmeta.get("file_size_bytes", 0),
                ),
                metadata={
                    "filename": fname,
                    "encryption_note": "Raycast main DB is encrypted; content not extracted",
                    "content_accessible": False,
                },
            ))

        return results
