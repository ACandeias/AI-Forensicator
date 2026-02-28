"""Collector for Continue.dev artifacts (~/.continue/).

Continue is an open-source AI code assistant that integrates with
VS Code and JetBrains IDEs.
"""

import json
import os
from typing import Any, Dict, List, Optional

from collectors.base import AbstractCollector
from config import HOME
from normalizer import sanitize_content, estimate_model_from_content


class ContinueDevCollector(AbstractCollector):
    """Collect artifacts from the Continue.dev AI assistant.

    Artifact root: ~/.continue/
    Key files: config.yaml, sessions/ (JSON), dev_data/ directory.
    """

    def __init__(self) -> None:
        super().__init__()
        self._root = os.path.join(HOME, ".continue")

    @property
    def name(self) -> str:
        return "continue_dev"

    def detect(self) -> bool:
        return os.path.isdir(self._root)

    def collect(self) -> List:
        artifacts = []  # type: List[Any]
        artifacts.extend(self._collect_config())
        artifacts.extend(self._collect_sessions())
        artifacts.extend(self._collect_dev_data())
        return artifacts

    # ------------------------------------------------------------------
    # 1. config.yaml / config.json -- Continue configuration
    # ------------------------------------------------------------------
    def _collect_config(self) -> List:
        """Parse config.yaml or config.json. Redact API keys.
        Artifact type: config."""
        results = []  # type: List[Any]

        config_candidates = [
            os.path.join(self._root, "config.yaml"),
            os.path.join(self._root, "config.yml"),
            os.path.join(self._root, "config.json"),
        ]

        for path in config_candidates:
            if not os.path.isfile(path) or os.path.islink(path):
                continue

            fmeta = self._file_metadata(path)
            file_hash = self._hash_file(path)

            if path.endswith(".json"):
                data = self._safe_read_json(path)
                if data is not None:
                    raw_text = json.dumps(data)
                else:
                    raw_text = self._safe_read_text(path) or ""
            else:
                raw_text = self._safe_read_text(path) or ""

            # Sanitize to redact API keys and credentials
            sanitized = sanitize_content(raw_text)

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
                    "filename": os.path.basename(path),
                    "credential_risk": self._contains_credentials(raw_text),
                    "security_note": "API keys redacted from content"
                    if self._contains_credentials(raw_text) else None,
                },
            ))

        return results

    # ------------------------------------------------------------------
    # 2. sessions/ -- conversation session files (JSON)
    # ------------------------------------------------------------------
    def _collect_sessions(self) -> List:
        """Walk sessions/ directory for JSON session files.
        Artifact type: conversation."""
        results = []  # type: List[Any]
        sessions_dir = os.path.join(self._root, "sessions")
        if not os.path.isdir(sessions_dir):
            return results

        for dirpath, _dirnames, filenames in os.walk(sessions_dir):
            if os.path.islink(dirpath):
                continue
            for fname in filenames:
                if not fname.endswith(".json"):
                    continue
                fpath = os.path.join(dirpath, fname)
                if os.path.islink(fpath) or not os.path.isfile(fpath):
                    continue

                results.extend(self._parse_session_file(fpath))

        return results

    def _parse_session_file(self, fpath: str) -> List:
        """Parse a single Continue session JSON file."""
        results = []  # type: List[Any]
        data = self._safe_read_json(fpath)
        if data is None:
            return results

        fmeta = self._file_metadata(fpath)
        file_hash = self._hash_file(fpath)

        # Session ID from filename
        session_id = os.path.splitext(os.path.basename(fpath))[0]

        # Continue sessions store messages in a "history" or "messages" array
        messages = []  # type: List[Any]
        if isinstance(data, dict):
            messages = data.get("history", data.get("messages", []))
            if not isinstance(messages, list):
                messages = []

        preview_text = ""
        model = None  # type: Optional[str]
        message_count = len(messages)

        for msg in messages[:5]:
            if isinstance(msg, dict):
                content = msg.get("content", msg.get("text", ""))
                if content:
                    preview_text += str(content) + " "
                msg_model = msg.get("model")
                if msg_model and not model:
                    model = str(msg_model)

        if not model:
            # Check top-level model field
            if isinstance(data, dict):
                model = data.get("model")
        if not model and preview_text:
            model = estimate_model_from_content(preview_text)

        title = ""
        if isinstance(data, dict):
            title = data.get("title", data.get("name", ""))
        if title:
            preview_text = "[{}] {}".format(title, preview_text)

        sanitized_preview = sanitize_content(preview_text.strip())

        results.append(self._make_artifact(
            artifact_type="conversation",
            file_path=fpath,
            file_hash_sha256=file_hash,
            file_size_bytes=fmeta.get("file_size_bytes"),
            file_modified=fmeta.get("file_modified"),
            file_created=fmeta.get("file_created"),
            content_preview=self._content_preview(sanitized_preview),
            model_identified=model,
            conversation_id=session_id,
            token_estimate=self._estimate_tokens(preview_text),
            metadata={
                "session_id": session_id,
                "message_count": message_count,
                "title": title,
            },
        ))

        return results

    # ------------------------------------------------------------------
    # 3. dev_data/ -- development telemetry and data
    # ------------------------------------------------------------------
    def _collect_dev_data(self) -> List:
        """Walk dev_data/ directory for JSON and text files.
        Artifact type: analytics."""
        results = []  # type: List[Any]
        dev_data_dir = os.path.join(self._root, "dev_data")
        if not os.path.isdir(dev_data_dir):
            return results

        for dirpath, _dirnames, filenames in os.walk(dev_data_dir):
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

                # Try reading as JSON; fall back to text
                data = self._safe_read_json(fpath)
                if data is not None:
                    preview_text = json.dumps(data)
                else:
                    text = self._safe_read_text(fpath)
                    preview_text = text or ""

                sanitized = sanitize_content(preview_text)

                results.append(self._make_artifact(
                    artifact_type="analytics",
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
