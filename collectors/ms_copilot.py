"""Microsoft Copilot artifact collector."""

import json
import os
import plistlib
from typing import Any, List

from collectors.base import AbstractCollector
from config import HOME
from normalizer import sanitize_content
from schema import AIArtifact


class MSCopilotCollector(AbstractCollector):
    """Collect artifacts from Microsoft Copilot (sandboxed container).

    Artifact root: ~/Library/Containers/com.microsoft.copilot/
    NOTE: This is a sandboxed macOS app.  PermissionError is handled
    gracefully -- inaccessible directories are skipped.
    """

    def __init__(self) -> None:
        super().__init__()
        self._root = os.path.join(
            HOME, "Library", "Containers", "com.microsoft.copilot",
        )

    @property
    def name(self) -> str:
        return "ms_copilot"

    def detect(self) -> bool:
        return os.path.isdir(self._root)

    def collect(self) -> List[AIArtifact]:
        if not os.path.isdir(self._root):
            return []

        artifacts = []  # type: List[Any]
        artifacts.extend(self._collect_json_and_plist_files())
        return artifacts

    # ------------------------------------------------------------------
    # 1. Walk for JSON and plist files
    # ------------------------------------------------------------------
    def _collect_json_and_plist_files(self) -> List[AIArtifact]:
        """Walk the sandboxed container for JSON and plist files.
        Handles PermissionError gracefully for inaccessible directories.
        Artifact type: config."""
        results = []  # type: List[AIArtifact]

        try:
            dir_walker = os.walk(self._root)
        except (OSError, PermissionError):
            return results

        for dirpath, _dirnames, filenames in dir_walker:
            if os.path.islink(dirpath):
                continue
            for fname in filenames:
                if not (fname.endswith(".json") or fname.endswith(".plist")):
                    continue
                fpath = os.path.join(dirpath, fname)
                if os.path.islink(fpath) or not os.path.isfile(fpath):
                    continue
                if self._is_credential_file(fpath):
                    continue

                try:
                    fmeta = self._file_metadata(fpath)
                    file_hash = self._hash_file(fpath)
                except (OSError, PermissionError):
                    continue

                if fname.endswith(".json"):
                    data = self._safe_read_json(fpath)
                    if data is None:
                        continue
                    sanitized = sanitize_content(
                        json.dumps(data, default=str)
                    )
                elif fname.endswith(".plist"):
                    try:
                        with open(fpath, "rb") as f:
                            plist_data = plistlib.load(f)
                        sanitized = sanitize_content(
                            json.dumps(
                                self._plist_to_safe(plist_data), default=str,
                            )
                        )
                    except (plistlib.InvalidFileException, OSError,
                            PermissionError, ValueError):
                        continue
                else:
                    continue

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
                        "sandbox_container": "com.microsoft.copilot",
                    },
                ))

        return results

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _plist_to_safe(obj):
        """Convert plist data types to JSON-serializable types."""
        if isinstance(obj, dict):
            return {
                str(k): MSCopilotCollector._plist_to_safe(v)
                for k, v in obj.items()
            }
        if isinstance(obj, (list, tuple)):
            return [MSCopilotCollector._plist_to_safe(item) for item in obj]
        if isinstance(obj, bytes):
            if len(obj) <= 64:
                return "<binary:{}>".format(obj.hex())
            return "<binary:{}... ({} bytes)>".format(
                obj[:32].hex(), len(obj),
            )
        if isinstance(obj, (int, float, str, bool)):
            return obj
        return str(obj)
