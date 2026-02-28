"""Collector for GitHub Copilot application artifacts.

Path: ~/Library/Application Support/GitHub Copilot/
Collects JSON configuration files and usage data.
"""

import json
import os
from typing import Any, Dict, List, Optional

from collectors.base import AbstractCollector
from config import ARTIFACT_PATHS, HOME
from normalizer import sanitize_content


class CopilotCollector(AbstractCollector):
    """Collect artifacts from the GitHub Copilot desktop application.

    Artifact root: ~/Library/Application Support/GitHub Copilot/
    Contains JSON config files and usage/telemetry data.
    """

    def __init__(self) -> None:
        super().__init__()
        self._root = ARTIFACT_PATHS.get(
            "copilot",
            os.path.join(HOME, "Library", "Application Support", "GitHub Copilot"),
        )

    @property
    def name(self) -> str:
        return "copilot"

    def detect(self) -> bool:
        return os.path.isdir(self._root)

    def collect(self) -> List:
        artifacts = []  # type: List[Any]
        artifacts.extend(self._collect_config_files())
        artifacts.extend(self._collect_usage_data())
        return artifacts

    # ------------------------------------------------------------------
    # 1. JSON config files
    # ------------------------------------------------------------------
    def _collect_config_files(self) -> List:
        """Collect JSON configuration files from the root directory.
        Artifact type: config."""
        results = []  # type: List[Any]
        config_names = {
            "settings.json", "config.json", "preferences.json",
            "hosts.json", "apps.json", "versions.json",
        }

        try:
            entries = os.listdir(self._root)
        except OSError:
            return results

        for fname in entries:
            if not fname.endswith(".json"):
                continue
            fpath = os.path.join(self._root, fname)
            if os.path.islink(fpath) or not os.path.isfile(fpath):
                continue
            if self._is_credential_file(fpath):
                continue

            data = self._safe_read_json(fpath)
            if data is None:
                continue

            fmeta = self._file_metadata(fpath)
            file_hash = self._hash_file(fpath)

            # Redact token/auth values if present
            redacted_data = self._redact_sensitive_keys(data)
            sanitized = sanitize_content(json.dumps(redacted_data))

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
                    "config_file": fname,
                    "key_count": len(data) if isinstance(data, dict) else 0,
                },
            ))

        return results

    # ------------------------------------------------------------------
    # 2. Usage / telemetry data
    # ------------------------------------------------------------------
    def _collect_usage_data(self) -> List:
        """Walk subdirectories for usage and telemetry data files.
        Artifact type: usage_data."""
        results = []  # type: List[Any]

        for dirpath, dirnames, filenames in os.walk(self._root):
            if os.path.islink(dirpath):
                continue
            # Filter out directories we should not descend into
            dirnames[:] = [
                d for d in dirnames
                if not os.path.islink(os.path.join(dirpath, d))
            ]

            for fname in filenames:
                # Skip root-level JSON files (already handled in config)
                if dirpath == self._root and fname.endswith(".json"):
                    continue
                if not (fname.endswith(".json") or fname.endswith(".jsonl")):
                    continue

                fpath = os.path.join(dirpath, fname)
                if os.path.islink(fpath) or not os.path.isfile(fpath):
                    continue
                if self._is_credential_file(fpath):
                    continue

                fmeta = self._file_metadata(fpath)
                file_hash = self._hash_file(fpath)

                if fname.endswith(".jsonl"):
                    # Collect JSONL summary
                    line_count = 0
                    first_preview = ""
                    for entry in self._safe_read_jsonl(fpath):
                        line_count += 1
                        if line_count == 1:
                            first_preview = self._content_preview(json.dumps(entry))

                    results.append(self._make_artifact(
                        artifact_type="usage_data",
                        file_path=fpath,
                        file_hash_sha256=file_hash,
                        file_size_bytes=fmeta.get("file_size_bytes"),
                        file_modified=fmeta.get("file_modified"),
                        file_created=fmeta.get("file_created"),
                        content_preview="JSONL: {} entries. First: {}".format(
                            line_count, first_preview,
                        ),
                        metadata={
                            "filename": fname,
                            "relative_path": os.path.relpath(fpath, self._root),
                            "entry_count": line_count,
                        },
                    ))
                else:
                    data = self._safe_read_json(fpath)
                    if data is None:
                        continue

                    redacted_data = self._redact_sensitive_keys(data)
                    sanitized = sanitize_content(json.dumps(redacted_data))

                    results.append(self._make_artifact(
                        artifact_type="usage_data",
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
    # helpers
    # ------------------------------------------------------------------
    def _redact_sensitive_keys(self, obj: Any) -> Any:
        """Recursively redact values for keys that look like tokens or secrets."""
        sensitive_keys = {"token", "oauth_token", "access_token", "secret",
                          "password", "auth", "credential", "api_key"}
        if isinstance(obj, dict):
            result = {}  # type: Dict[str, Any]
            for key, value in obj.items():
                if key.lower() in sensitive_keys:
                    result[key] = "[REDACTED]"
                else:
                    result[key] = self._redact_sensitive_keys(value)
            return result
        if isinstance(obj, list):
            return [self._redact_sensitive_keys(item) for item in obj]
        return obj
