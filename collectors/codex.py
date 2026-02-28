"""Collector for OpenAI Codex CLI artifacts (~/.codex/).

Codex stores JSONL history files and configuration, following a similar
pattern to the Claude Code CLI.
"""

import json
import os
from typing import Any, Dict, List, Optional

from collectors.base import AbstractCollector
from config import ARTIFACT_PATHS, HOME
from normalizer import sanitize_content, estimate_model_from_content


class CodexCollector(AbstractCollector):
    """Collect artifacts from the OpenAI Codex CLI data directory.

    Artifact root: ~/.codex/
    Contains JSONL history files and configuration files.
    """

    def __init__(self) -> None:
        super().__init__()
        self._root = ARTIFACT_PATHS.get(
            "codex",
            os.path.join(HOME, ".codex"),
        )

    @property
    def name(self) -> str:
        return "codex"

    def detect(self) -> bool:
        return os.path.isdir(self._root)

    def collect(self) -> List:
        artifacts = []  # type: List[Any]
        artifacts.extend(self._collect_history())
        artifacts.extend(self._collect_sessions())
        artifacts.extend(self._collect_config_files())
        return artifacts

    # ------------------------------------------------------------------
    # 1. history.jsonl -- prompt history
    # ------------------------------------------------------------------
    def _collect_history(self) -> List:
        """Parse history.jsonl for prompt history entries.
        Artifact type: prompt_history."""
        results = []  # type: List[Any]
        path = os.path.join(self._root, "history.jsonl")
        if not os.path.isfile(path):
            return results

        fmeta = self._file_metadata(path)
        file_hash = self._hash_file(path)

        for entry in self._safe_read_jsonl(path):
            display = entry.get("display", entry.get("prompt", ""))
            ts = self._parse_timestamp_ms(entry.get("timestamp"))
            session_id = entry.get("sessionId", entry.get("session_id"))
            project = entry.get("project")

            results.append(self._make_artifact(
                artifact_type="prompt_history",
                timestamp=ts,
                file_path=path,
                file_hash_sha256=file_hash,
                file_size_bytes=fmeta.get("file_size_bytes"),
                file_modified=fmeta.get("file_modified"),
                file_created=fmeta.get("file_created"),
                content_preview=self._content_preview(display),
                conversation_id=session_id,
                token_estimate=self._estimate_tokens(display),
                metadata={
                    "session_id": session_id,
                    "project": project,
                    "display": display,
                },
            ))

        return results

    # ------------------------------------------------------------------
    # 2. Session JSONL files (projects/*/*.jsonl or sessions/*.jsonl)
    # ------------------------------------------------------------------
    def _collect_sessions(self) -> List:
        """Walk for session JSONL files and parse conversation messages.
        Artifact type: conversation_message."""
        results = []  # type: List[Any]

        # Check common session directories
        session_dirs = [
            os.path.join(self._root, "projects"),
            os.path.join(self._root, "sessions"),
        ]

        for session_dir in session_dirs:
            if not os.path.isdir(session_dir):
                continue
            for dirpath, _dirnames, filenames in os.walk(session_dir):
                if os.path.islink(dirpath):
                    continue
                for fname in filenames:
                    if not fname.endswith(".jsonl"):
                        continue
                    fpath = os.path.join(dirpath, fname)
                    if os.path.islink(fpath) or not os.path.isfile(fpath):
                        continue
                    results.extend(self._parse_session_file(fpath))

        return results

    def _parse_session_file(self, fpath: str) -> List:
        """Process a single session JSONL file line-by-line."""
        results = []  # type: List[Any]
        fmeta = self._file_metadata(fpath)
        file_hash = self._hash_file(fpath)

        # Derive session id from filename (strip .jsonl)
        session_id = os.path.splitext(os.path.basename(fpath))[0]

        for entry in self._safe_read_jsonl(fpath):
            msg_type = entry.get("type", entry.get("role", ""))
            if msg_type not in ("user", "assistant", "system"):
                continue

            message = entry.get("message", entry)
            if not isinstance(message, dict):
                continue

            # Content can be a string or a list of content blocks
            raw_content = message.get("content", "")
            if isinstance(raw_content, list):
                text_parts = []
                for block in raw_content:
                    if isinstance(block, dict):
                        text_parts.append(block.get("text", ""))
                    elif isinstance(block, str):
                        text_parts.append(block)
                content_text = "\n".join(text_parts)
            else:
                content_text = str(raw_content)

            model = message.get("model") or estimate_model_from_content(content_text)
            ts = self._parse_timestamp_ms(entry.get("timestamp"))

            results.append(self._make_artifact(
                artifact_type="conversation_message",
                timestamp=ts,
                file_path=fpath,
                file_hash_sha256=file_hash,
                file_size_bytes=fmeta.get("file_size_bytes"),
                file_modified=fmeta.get("file_modified"),
                file_created=fmeta.get("file_created"),
                content_preview=self._content_preview(content_text),
                message_role=msg_type,
                model_identified=model,
                conversation_id=session_id,
                token_estimate=self._estimate_tokens(content_text),
                metadata={
                    "session_id": session_id,
                    "message_type": msg_type,
                },
            ))

        return results

    # ------------------------------------------------------------------
    # 3. Config files (settings.json, config.json, etc.)
    # ------------------------------------------------------------------
    def _collect_config_files(self) -> List:
        """Collect JSON config files in the root directory.
        Artifact type: config."""
        results = []  # type: List[Any]
        config_names = {
            "settings.json", "config.json", "preferences.json",
            "config.yaml", "config.yml",
        }

        try:
            entries = os.listdir(self._root)
        except OSError:
            return results

        for fname in entries:
            if fname not in config_names:
                continue
            fpath = os.path.join(self._root, fname)
            if os.path.islink(fpath) or not os.path.isfile(fpath):
                continue
            if self._is_credential_file(fpath):
                continue

            data = self._safe_read_json(fpath)
            if data is None:
                # Try as text for YAML files
                text = self._safe_read_text(fpath)
                if text is None:
                    continue
                fmeta = self._file_metadata(fpath)
                file_hash = self._hash_file(fpath)
                sanitized = sanitize_content(text)

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
                    },
                ))
                continue

            fmeta = self._file_metadata(fpath)
            file_hash = self._hash_file(fpath)

            # Check for env key (credential risk) and redact
            has_env_block = "env" in data if isinstance(data, dict) else False
            env_keys = []  # type: List[str]
            if has_env_block and isinstance(data.get("env"), dict):
                env_keys = list(data["env"].keys())
                sanitized_data = dict(data)
                sanitized_data["env"] = {k: "[REDACTED]" for k in env_keys}
            else:
                sanitized_data = data

            sanitized = sanitize_content(json.dumps(sanitized_data))

            results.append(self._make_artifact(
                artifact_type="config",
                file_path=fpath,
                file_hash_sha256=file_hash,
                file_size_bytes=fmeta.get("file_size_bytes"),
                file_modified=fmeta.get("file_modified"),
                file_created=fmeta.get("file_created"),
                content_preview=self._content_preview(sanitized),
                raw_data=sanitized,
                metadata={
                    "config_file": fname,
                    "has_env_block": has_env_block,
                    "env_variable_names": env_keys,
                    "key_count": len(data) if isinstance(data, dict) else 0,
                },
            ))

        return results
