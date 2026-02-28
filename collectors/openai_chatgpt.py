"""Collector for ChatGPT macOS app artifacts (~/Library/Group Containers/group.com.openai.chat/)."""

import json
import os
import plistlib
from typing import Any, Dict, List, Optional

from collectors.base import AbstractCollector
from config import ARTIFACT_PATHS
from normalizer import normalize_timestamp, sanitize_content


class ChatGPTCollector(AbstractCollector):
    """Collect artifacts from the ChatGPT macOS application.

    Artifact root: ~/Library/Group Containers/group.com.openai.chat/
    NOTE: .data files are CK-encrypted binary -- we collect metadata only
    (file count, sizes, timestamps), NOT content.
    """

    def __init__(self) -> None:
        super().__init__()
        self._root = ARTIFACT_PATHS["chatgpt"]

    @property
    def name(self) -> str:
        return "ChatGPT"

    def detect(self) -> bool:
        return os.path.isdir(self._root)

    def collect(self) -> List:
        artifacts = []  # type: List[Any]
        artifacts.extend(self._collect_encrypted_conversations())
        artifacts.extend(self._collect_preferences())
        return artifacts

    # ------------------------------------------------------------------
    # 1. .data files -- CK-encrypted binary (metadata only)
    # ------------------------------------------------------------------
    def _collect_encrypted_conversations(self) -> List:
        """Walk the directory for .data files.  These are CK-encrypted binary
        and cannot be decrypted without CloudKit keys, so we collect metadata
        only: file count, sizes, timestamps.
        Artifact type: encrypted_conversation."""
        results = []  # type: List[Any]

        data_files = []  # type: List[Dict[str, Any]]
        total_size = 0

        for dirpath, _dirnames, filenames in os.walk(self._root):
            for fname in filenames:
                if not fname.endswith(".data"):
                    continue
                fpath = os.path.join(dirpath, fname)
                if not os.path.isfile(fpath):
                    continue

                fmeta = self._file_metadata(fpath)
                size = fmeta.get("file_size_bytes") or 0
                total_size += size

                data_files.append({
                    "filename": fname,
                    "path": fpath,
                    "size_bytes": size,
                    "modified": fmeta.get("file_modified"),
                    "created": fmeta.get("file_created"),
                })

        if not data_files:
            return results

        # Sort by modification time (most recent first)
        data_files.sort(
            key=lambda x: x.get("modified") or "",
            reverse=True,
        )

        # Create one summary artifact for all encrypted data files
        results.append(self._make_artifact(
            artifact_type="encrypted_conversation",
            file_path=self._root,
            content_preview="ChatGPT: {} encrypted .data files, {:.1f} MB total".format(
                len(data_files),
                total_size / (1024 * 1024),
            ),
            metadata={
                "file_count": len(data_files),
                "total_size_bytes": total_size,
                "total_size_mb": round(total_size / (1024 * 1024), 2),
                "encryption_type": "CloudKit (CK-encrypted)",
                "content_accessible": False,
                "newest_file": data_files[0] if data_files else None,
                "oldest_file": data_files[-1] if data_files else None,
                "security_note": "Files are CK-encrypted; content not extracted",
            },
        ))

        # Also create per-file metadata artifacts for the individual .data files
        for df in data_files:
            file_hash = self._hash_file(df["path"])
            results.append(self._make_artifact(
                artifact_type="encrypted_conversation",
                file_path=df["path"],
                file_hash_sha256=file_hash,
                file_size_bytes=df.get("size_bytes"),
                file_modified=df.get("modified"),
                file_created=df.get("created"),
                content_preview="Encrypted .data file: {} ({} bytes)".format(
                    df["filename"], df.get("size_bytes", 0),
                ),
                metadata={
                    "filename": df["filename"],
                    "encryption_type": "CloudKit (CK-encrypted)",
                    "content_accessible": False,
                },
            ))

        return results

    # ------------------------------------------------------------------
    # 2. com.openai.chat.plist -- preferences
    # ------------------------------------------------------------------
    def _collect_preferences(self) -> List:
        """Parse com.openai.chat.plist with plistlib for user preferences.
        Artifact type: preferences."""
        results = []  # type: List[Any]

        # The plist may be in the root or in a Library/Preferences subfolder
        candidate_paths = [
            os.path.join(self._root, "com.openai.chat.plist"),
            os.path.join(
                self._root, "Library", "Preferences", "com.openai.chat.plist"
            ),
        ]

        for path in candidate_paths:
            if not os.path.isfile(path):
                continue

            fmeta = self._file_metadata(path)
            file_hash = self._hash_file(path)

            plist_data = self._safe_read_plist(path)
            if plist_data is None:
                continue

            # Convert plist data to a JSON-safe dict for storage
            safe_data = self._plist_to_json_safe(plist_data)

            # Sanitize any credential content
            sanitized_text = sanitize_content(json.dumps(safe_data, default=str))

            results.append(self._make_artifact(
                artifact_type="preferences",
                file_path=path,
                file_hash_sha256=file_hash,
                file_size_bytes=fmeta.get("file_size_bytes"),
                file_modified=fmeta.get("file_modified"),
                file_created=fmeta.get("file_created"),
                content_preview=self._content_preview(sanitized_text),
                raw_data=sanitized_text,
                metadata={
                    "plist_key_count": len(safe_data) if isinstance(safe_data, dict) else 0,
                    "plist_keys": list(safe_data.keys()) if isinstance(safe_data, dict) else [],
                },
            ))

        return results

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _safe_read_plist(self, path: str) -> Optional[Any]:
        """Safely read a plist file (binary or XML format)."""
        try:
            with open(path, "rb") as f:
                return plistlib.load(f)
        except (plistlib.InvalidFileException, OSError, IOError, Exception):
            return None

    def _plist_to_json_safe(self, obj: Any) -> Any:
        """Convert plist data types to JSON-serializable types."""
        if isinstance(obj, dict):
            return {str(k): self._plist_to_json_safe(v) for k, v in obj.items()}
        if isinstance(obj, (list, tuple)):
            return [self._plist_to_json_safe(item) for item in obj]
        if isinstance(obj, bytes):
            # Represent binary data as hex preview
            if len(obj) <= 64:
                return "<binary:{}>".format(obj.hex())
            return "<binary:{}... ({} bytes)>".format(obj[:32].hex(), len(obj))
        if isinstance(obj, (int, float, str, bool)):
            return obj
        # datetime and other types
        return str(obj)
