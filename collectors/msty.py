"""Msty local LLM runner artifact collector (~/Library/Application Support/Msty/)."""

import json
import os
from typing import Any, Dict, List, Optional

from collectors.base import AbstractCollector
from collectors.mixins import LocalLLMRunnerMixin
from config import HOME
from normalizer import sanitize_content, estimate_model_from_content
from schema import AIArtifact


class MstyCollector(LocalLLMRunnerMixin, AbstractCollector):
    """Collect artifacts from the Msty local LLM runner.

    Artifact root: ~/Library/Application Support/Msty/
    Collects chat history and model configs by walking for JSON files.
    Does NOT read binary model files.
    """

    def __init__(self) -> None:
        super().__init__()
        self._root = os.path.join(
            HOME, "Library", "Application Support", "Msty",
        )

    @property
    def name(self) -> str:
        return "msty"

    def detect(self) -> bool:
        return os.path.exists(self._root)

    def collect(self) -> List[AIArtifact]:
        artifacts = []  # type: List[Any]
        artifacts.extend(self._collect_chat_history())
        artifacts.extend(self._collect_model_configs())
        return artifacts

    # ------------------------------------------------------------------
    # 1. Chat history -- walk for JSON conversation files
    # ------------------------------------------------------------------
    def _collect_chat_history(self) -> List:
        """Walk the Msty data directory for chat history JSON files.

        Looks for conversation data in chats/, conversations/, or
        threads/ subdirectories.
        Returns List[AIArtifact].
        """
        results = []  # type: List[Any]
        if not os.path.isdir(self._root):
            return results

        # Known chat-related subdirectories
        chat_dirs = ["chats", "conversations", "threads", "history"]
        found_chat_dir = False

        for subdir in chat_dirs:
            chat_path = os.path.join(self._root, subdir)
            if os.path.isdir(chat_path):
                found_chat_dir = True
                results.extend(self._walk_chat_dir(chat_path, subdir))

        # If no known subdirectory found, scan root for chat-related JSON files
        if not found_chat_dir:
            results.extend(self._walk_chat_dir(self._root, "root"))

        return results

    def _walk_chat_dir(self, directory, source_label) -> List:
        """Walk a directory for JSON conversation files.

        Returns List[AIArtifact].
        """
        results = []  # type: List[Any]

        for dirpath, _dirnames, filenames in os.walk(directory):
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

                fmeta = self._file_metadata(fpath)
                file_hash = self._hash_file(fpath)

                data = self._safe_read_json(fpath)
                if data is None:
                    continue

                # Skip model config files in this pass (handled separately)
                rel_path = os.path.relpath(fpath, self._root)
                if rel_path.startswith("models"):
                    continue

                preview_text = ""
                model = None  # type: Optional[str]
                message_count = 0
                conversation_id = None  # type: Optional[str]

                if isinstance(data, dict):
                    title = data.get("title", data.get("name", ""))
                    model = data.get("model", data.get("model_id"))
                    conversation_id = str(
                        data.get("id", data.get("conversation_id", ""))
                    ) or None
                    messages = data.get("messages", data.get("conversation", []))
                    if isinstance(messages, list):
                        message_count = len(messages)
                        for msg in messages[:3]:
                            if isinstance(msg, dict):
                                content = msg.get("content", msg.get("text", ""))
                                if content:
                                    preview_text += str(content) + " "
                                if not model:
                                    model = msg.get("model")
                    if title:
                        preview_text = "[{}] {}".format(title, preview_text)

                elif isinstance(data, list):
                    message_count = len(data)
                    for msg in data[:3]:
                        if isinstance(msg, dict):
                            content = msg.get("content", msg.get("text", ""))
                            if content:
                                preview_text += str(content) + " "
                            if not model:
                                model = msg.get("model")

                if not model and preview_text:
                    model = estimate_model_from_content(preview_text)

                sanitized = sanitize_content(preview_text.strip())

                results.append(self._make_artifact(
                    artifact_type="conversation",
                    file_path=fpath,
                    file_hash_sha256=file_hash,
                    file_size_bytes=fmeta.get("file_size_bytes"),
                    file_modified=fmeta.get("file_modified"),
                    file_created=fmeta.get("file_created"),
                    content_preview=self._content_preview(sanitized),
                    model_identified=model,
                    conversation_id=conversation_id,
                    token_estimate=self._estimate_tokens(preview_text),
                    metadata={
                        "filename": fname,
                        "relative_path": rel_path,
                        "source_directory": source_label,
                        "message_count": message_count,
                    },
                ))

        return results

    # ------------------------------------------------------------------
    # 2. Model configs -- walk for JSON model configuration files
    # ------------------------------------------------------------------
    def _collect_model_configs(self) -> List:
        """Walk the Msty data directory for model configuration JSON files.

        Checks models/ subdirectory and falls back to scanning for
        model-related JSON at the root level.
        Returns List[AIArtifact].
        """
        results = []  # type: List[Any]

        # Check for a dedicated models directory first
        models_dir = os.path.join(self._root, "models")
        if os.path.isdir(models_dir):
            results.extend(
                self._collect_model_inventory(models_dir, tool_name="Msty")
            )
            return results

        # No models/ directory -- walk root for model config JSON files
        results.extend(self._walk_model_json_files())
        return results

    def _walk_model_json_files(self) -> List:
        """Walk the Msty root for model-related JSON config files.

        Returns List[AIArtifact].
        """
        results = []  # type: List[Any]
        if not os.path.isdir(self._root):
            return results

        model_keywords = {"model", "llm", "config", "settings"}

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

                # Only collect files that look model-related by name
                fname_lower = fname.lower()
                if not any(kw in fname_lower for kw in model_keywords):
                    continue

                fmeta = self._file_metadata(fpath)
                file_hash = self._hash_file(fpath)

                data = self._safe_read_json(fpath)
                if data is None:
                    continue

                sanitized = sanitize_content(json.dumps(data))
                rel_path = os.path.relpath(fpath, self._root)

                results.append(self._make_artifact(
                    artifact_type="model_config",
                    file_path=fpath,
                    file_hash_sha256=file_hash,
                    file_size_bytes=fmeta.get("file_size_bytes"),
                    file_modified=fmeta.get("file_modified"),
                    file_created=fmeta.get("file_created"),
                    content_preview=self._content_preview(sanitized),
                    raw_data=sanitized if len(sanitized) < 50000 else None,
                    metadata={
                        "filename": fname,
                        "relative_path": rel_path,
                    },
                ))

        return results
