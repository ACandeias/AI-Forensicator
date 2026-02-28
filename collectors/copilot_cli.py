"""Collector for GitHub Copilot CLI artifacts (~/.copilot/).

This covers the Copilot CLI tool (gh copilot), not the VS Code
extension or the desktop Copilot app (which are separate collectors).
"""

import json
import os
from typing import Any, Dict, List, Optional

from collectors.base import AbstractCollector
from config import HOME
from normalizer import sanitize_content


class CopilotCLICollector(AbstractCollector):
    """Collect artifacts from the GitHub Copilot CLI assistant.

    Artifact root: ~/.copilot/
    Key files: command-history-state.json, session-state/ directory,
    mcp-config.json.
    """

    def __init__(self) -> None:
        super().__init__()
        self._root = os.path.join(HOME, ".copilot")

    @property
    def name(self) -> str:
        return "copilot_cli"

    def detect(self) -> bool:
        return os.path.isdir(self._root)

    def collect(self) -> List:
        artifacts = []  # type: List[Any]
        artifacts.extend(self._collect_command_history())
        artifacts.extend(self._collect_session_state())
        artifacts.extend(self._collect_mcp_config())
        return artifacts

    # ------------------------------------------------------------------
    # 1. command-history-state.json -- CLI command history
    # ------------------------------------------------------------------
    def _collect_command_history(self) -> List:
        """Parse command-history-state.json for CLI usage history.
        Artifact type: prompt_history."""
        results = []  # type: List[Any]
        path = os.path.join(self._root, "command-history-state.json")
        if not os.path.isfile(path) or os.path.islink(path):
            return results

        data = self._safe_read_json(path)
        if data is None:
            return results

        fmeta = self._file_metadata(path)
        file_hash = self._hash_file(path)

        # The history file may be a list of entries or a dict with a history key
        entries = []  # type: List[Any]
        if isinstance(data, list):
            entries = data
        elif isinstance(data, dict):
            entries = data.get("history", data.get("commands", data.get("entries", [])))
            if not isinstance(entries, list):
                entries = []

        if entries:
            # Create individual artifacts for each history entry
            for entry in entries:
                if not isinstance(entry, dict):
                    continue

                command = entry.get("command", entry.get("query", entry.get("input", "")))
                ts = self._parse_timestamp_ms(
                    entry.get("timestamp", entry.get("time")),
                )
                suggestion = entry.get("suggestion", entry.get("output", entry.get("result", "")))

                preview_text = str(command)
                if suggestion:
                    preview_text = "{} -> {}".format(command, suggestion)

                sanitized = sanitize_content(preview_text)

                results.append(self._make_artifact(
                    artifact_type="prompt_history",
                    timestamp=ts,
                    file_path=path,
                    file_hash_sha256=file_hash,
                    file_size_bytes=fmeta.get("file_size_bytes"),
                    file_modified=fmeta.get("file_modified"),
                    file_created=fmeta.get("file_created"),
                    content_preview=self._content_preview(sanitized),
                    token_estimate=self._estimate_tokens(preview_text),
                    metadata={
                        "command": str(command) if command else None,
                        "has_suggestion": bool(suggestion),
                    },
                ))
        else:
            # Fallback: treat the entire file as a single artifact
            sanitized = sanitize_content(json.dumps(data))

            results.append(self._make_artifact(
                artifact_type="prompt_history",
                file_path=path,
                file_hash_sha256=file_hash,
                file_size_bytes=fmeta.get("file_size_bytes"),
                file_modified=fmeta.get("file_modified"),
                file_created=fmeta.get("file_created"),
                content_preview=self._content_preview(sanitized),
                raw_data=sanitized if len(sanitized) < 50000 else None,
                metadata={
                    "filename": "command-history-state.json",
                },
            ))

        return results

    # ------------------------------------------------------------------
    # 2. session-state/ -- session state files
    # ------------------------------------------------------------------
    def _collect_session_state(self) -> List:
        """Walk session-state/ directory for session data files.
        Artifact type: session_storage."""
        results = []  # type: List[Any]
        session_dir = os.path.join(self._root, "session-state")
        if not os.path.isdir(session_dir):
            return results

        for dirpath, _dirnames, filenames in os.walk(session_dir):
            if os.path.islink(dirpath):
                continue
            for fname in filenames:
                fpath = os.path.join(dirpath, fname)
                if os.path.islink(fpath) or not os.path.isfile(fpath):
                    continue
                if self._is_credential_file(fpath):
                    continue

                fmeta = self._file_metadata(fpath)
                file_hash = self._hash_file(fpath)

                # Try reading as JSON first; fall back to text
                data = self._safe_read_json(fpath)
                if data is not None:
                    preview_text = json.dumps(data)
                else:
                    text = self._safe_read_text(fpath)
                    preview_text = text or ""

                sanitized = sanitize_content(preview_text)

                # Derive session ID from filename
                session_id = os.path.splitext(fname)[0]

                results.append(self._make_artifact(
                    artifact_type="session_storage",
                    file_path=fpath,
                    file_hash_sha256=file_hash,
                    file_size_bytes=fmeta.get("file_size_bytes"),
                    file_modified=fmeta.get("file_modified"),
                    file_created=fmeta.get("file_created"),
                    content_preview=self._content_preview(sanitized),
                    raw_data=sanitized if len(sanitized) < 50000 else None,
                    conversation_id=session_id,
                    metadata={
                        "filename": fname,
                        "session_id": session_id,
                        "relative_path": os.path.relpath(fpath, session_dir),
                    },
                ))

        return results

    def _redact_env_values(self, obj):
        """Recursively redact values in 'env' dict blocks."""
        if isinstance(obj, dict):
            result = {}
            for key, value in obj.items():
                if key == "env" and isinstance(value, dict):
                    result[key] = {k: "[REDACTED]" for k in value}
                else:
                    result[key] = self._redact_env_values(value)
            return result
        if isinstance(obj, list):
            return [self._redact_env_values(item) for item in obj]
        return obj

    # ------------------------------------------------------------------
    # 3. mcp-config.json -- MCP (Model Context Protocol) configuration
    # ------------------------------------------------------------------
    def _collect_mcp_config(self) -> List:
        """Parse mcp-config.json for MCP tool configuration.
        Artifact type: config."""
        results = []  # type: List[Any]
        path = os.path.join(self._root, "mcp-config.json")
        if not os.path.isfile(path) or os.path.islink(path):
            return results

        data = self._safe_read_json(path)
        if data is None:
            return results

        fmeta = self._file_metadata(path)
        file_hash = self._hash_file(path)

        # Redact env values in MCP config before sanitization
        redacted_data = self._redact_env_values(data)
        raw_text = json.dumps(redacted_data)
        sanitized = sanitize_content(raw_text)

        # Extract summary info about MCP configuration
        server_count = 0
        server_names = []  # type: List[str]
        if isinstance(data, dict):
            servers = data.get("mcpServers", data.get("servers", {}))
            if isinstance(servers, dict):
                server_count = len(servers)
                server_names = list(servers.keys())

        results.append(self._make_artifact(
            artifact_type="config",
            file_path=path,
            file_hash_sha256=file_hash,
            file_size_bytes=fmeta.get("file_size_bytes"),
            file_modified=fmeta.get("file_modified"),
            file_created=fmeta.get("file_created"),
            content_preview=self._content_preview(sanitized),
            raw_data=sanitized if len(sanitized) < 50000 else None,
            metadata={
                "filename": "mcp-config.json",
                "mcp_server_count": server_count,
                "mcp_server_names": server_names,
                "env_values_redacted": True,
            },
        ))

        return results
