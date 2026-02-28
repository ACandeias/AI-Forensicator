"""Collector for Amazon Q Developer (formerly CodeWhisperer) artifacts.

Paths:
  ~/.aws/amazonq/history/     -- chat history JSON files
  ~/.amazonq/                 -- Amazon Q CLI config and data
"""

import json
import os
from typing import Any, Dict, List, Optional

from collectors.base import AbstractCollector
from config import HOME
from normalizer import sanitize_content, estimate_model_from_content


class AmazonQCollector(AbstractCollector):
    """Collect artifacts from the Amazon Q Developer CLI assistant.

    Amazon Q stores chat history as JSON files named chat-history-<hash>.json
    under ~/.aws/amazonq/history/.  Additional config and todo lists live
    under ~/.amazonq/.
    """

    def __init__(self) -> None:
        super().__init__()
        self._history_root = os.path.join(HOME, ".aws", "amazonq", "history")
        self._amazonq_root = os.path.join(HOME, ".amazonq")

    @property
    def name(self) -> str:
        return "amazon_q"

    def detect(self) -> bool:
        return os.path.isdir(self._history_root) or os.path.isdir(self._amazonq_root)

    def collect(self) -> List:
        artifacts = []  # type: List[Any]
        artifacts.extend(self._collect_chat_history())
        artifacts.extend(self._collect_cli_config())
        artifacts.extend(self._collect_todo_lists())
        return artifacts

    # ------------------------------------------------------------------
    # 1. ~/.aws/amazonq/history/ -- JSON chat history files
    # ------------------------------------------------------------------
    def _collect_chat_history(self) -> List:
        """Collect chat-history-<hash>.json files.
        Artifact type: conversation."""
        results = []  # type: List[Any]
        if not os.path.isdir(self._history_root):
            return results

        for dirpath, _dirnames, filenames in os.walk(self._history_root):
            if os.path.islink(dirpath):
                continue
            for fname in filenames:
                if not fname.endswith(".json"):
                    continue
                fpath = os.path.join(dirpath, fname)
                if os.path.islink(fpath) or not os.path.isfile(fpath):
                    continue

                results.extend(self._parse_chat_history_file(fpath, fname))

        return results

    def _parse_chat_history_file(self, fpath: str, fname: str) -> List:
        """Parse a single Amazon Q chat history JSON file."""
        results = []  # type: List[Any]
        data = self._safe_read_json(fpath)
        if data is None:
            return results

        fmeta = self._file_metadata(fpath)
        file_hash = self._hash_file(fpath)

        # Derive conversation ID from filename (chat-history-<hash>.json)
        conversation_id = fname.replace("chat-history-", "").replace(".json", "")

        # Amazon Q history files can be a list of messages or a dict with messages
        messages = []  # type: List[Any]
        if isinstance(data, list):
            messages = data
        elif isinstance(data, dict):
            messages = data.get("messages", data.get("history", []))
            if not isinstance(messages, list):
                messages = []

        preview_text = ""
        model = None  # type: Optional[str]
        message_count = len(messages)

        for msg in messages[:5]:
            if isinstance(msg, dict):
                content = msg.get("content", msg.get("body", msg.get("text", "")))
                if content:
                    preview_text += str(content) + " "
                msg_model = msg.get("model")
                if msg_model and not model:
                    model = str(msg_model)

        if not model and isinstance(data, dict):
            model = data.get("model")
        if not model and preview_text:
            model = estimate_model_from_content(preview_text)

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
            conversation_id=conversation_id,
            token_estimate=self._estimate_tokens(preview_text),
            metadata={
                "filename": fname,
                "message_count": message_count,
                "conversation_id": conversation_id,
            },
        ))

        return results

    # ------------------------------------------------------------------
    # 2. ~/.amazonq/ config files
    # ------------------------------------------------------------------
    def _collect_cli_config(self) -> List:
        """Collect Amazon Q CLI configuration files.
        Artifact type: config."""
        results = []  # type: List[Any]
        if not os.path.isdir(self._amazonq_root):
            return results

        config_extensions = (".json", ".yaml", ".yml", ".toml", ".ini", ".cfg")

        for dirpath, _dirnames, filenames in os.walk(self._amazonq_root):
            if os.path.islink(dirpath):
                continue
            for fname in filenames:
                if not any(fname.endswith(ext) for ext in config_extensions):
                    continue
                fpath = os.path.join(dirpath, fname)
                if os.path.islink(fpath) or not os.path.isfile(fpath):
                    continue
                if self._is_credential_file(fpath):
                    continue

                # Skip the history directory (handled separately)
                if "history" in os.path.relpath(fpath, self._amazonq_root).split(os.sep):
                    continue

                fmeta = self._file_metadata(fpath)
                file_hash = self._hash_file(fpath)

                data = self._safe_read_json(fpath)
                if data is not None:
                    raw_text = json.dumps(data)
                else:
                    raw_text = self._safe_read_text(fpath) or ""

                sanitized = sanitize_content(raw_text)

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
                        "relative_path": os.path.relpath(fpath, self._amazonq_root),
                        "credential_risk": self._contains_credentials(raw_text),
                    },
                ))

        return results

    # ------------------------------------------------------------------
    # 3. Todo lists and task files
    # ------------------------------------------------------------------
    def _collect_todo_lists(self) -> List:
        """Collect Amazon Q todo/task list files.
        Artifact type: task_data."""
        results = []  # type: List[Any]

        # Check both roots for todo-related files
        search_dirs = []  # type: List[str]
        if os.path.isdir(self._amazonq_root):
            search_dirs.append(self._amazonq_root)

        # Also check ~/.aws/amazonq/ for any todo files
        aws_amazonq = os.path.join(HOME, ".aws", "amazonq")
        if os.path.isdir(aws_amazonq):
            search_dirs.append(aws_amazonq)

        seen_paths = set()  # type: set

        for search_dir in search_dirs:
            for dirpath, _dirnames, filenames in os.walk(search_dir):
                if os.path.islink(dirpath):
                    continue
                for fname in filenames:
                    fpath = os.path.join(dirpath, fname)
                    if fpath in seen_paths:
                        continue
                    seen_paths.add(fpath)

                    # Look for todo/task related files
                    fname_lower = fname.lower()
                    if not ("todo" in fname_lower or "task" in fname_lower):
                        continue
                    if not fname.endswith(".json"):
                        continue
                    if os.path.islink(fpath) or not os.path.isfile(fpath):
                        continue
                    if self._is_credential_file(fpath):
                        continue

                    fmeta = self._file_metadata(fpath)
                    file_hash = self._hash_file(fpath)

                    data = self._safe_read_json(fpath)
                    if data is None:
                        continue

                    sanitized = sanitize_content(json.dumps(data))

                    # Count items if data is a list
                    item_count = 0
                    if isinstance(data, list):
                        item_count = len(data)
                    elif isinstance(data, dict):
                        items = data.get("items", data.get("todos", data.get("tasks", [])))
                        if isinstance(items, list):
                            item_count = len(items)

                    results.append(self._make_artifact(
                        artifact_type="task_data",
                        file_path=fpath,
                        file_hash_sha256=file_hash,
                        file_size_bytes=fmeta.get("file_size_bytes"),
                        file_modified=fmeta.get("file_modified"),
                        file_created=fmeta.get("file_created"),
                        content_preview=self._content_preview(sanitized),
                        raw_data=sanitized if len(sanitized) < 50000 else None,
                        metadata={
                            "filename": fname,
                            "item_count": item_count,
                        },
                    ))

        return results
