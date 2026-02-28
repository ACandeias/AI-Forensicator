"""Jan local LLM runner artifact collector (~/jan/ or ~/Library/Application Support/Jan/)."""

import json
import os
from typing import Any, Dict, List, Optional

from collectors.base import AbstractCollector
from collectors.mixins import LocalLLMRunnerMixin
from config import HOME
from normalizer import sanitize_content, estimate_model_from_content
from schema import AIArtifact


class JanCollector(LocalLLMRunnerMixin, AbstractCollector):
    """Collect artifacts from the Jan local LLM runner.

    Artifact root: ~/jan/ or ~/Library/Application Support/Jan/
    Collects threads (JSON conversations), model configs, and app logs.
    """

    def __init__(self) -> None:
        super().__init__()
        self._root = self._find_root()

    def _find_root(self) -> Optional[str]:
        """Locate the Jan data directory."""
        candidates = [
            os.path.join(HOME, "jan"),
            os.path.join(HOME, "Library", "Application Support", "Jan"),
        ]
        for path in candidates:
            if os.path.isdir(path):
                return path
        return None

    @property
    def name(self) -> str:
        return "jan"

    def detect(self) -> bool:
        return self._root is not None and os.path.isdir(self._root)

    def collect(self) -> List[AIArtifact]:
        artifacts = []  # type: List[Any]
        if self._root is None:
            return artifacts
        artifacts.extend(self._collect_threads())
        artifacts.extend(self._collect_models())
        artifacts.extend(self._collect_app_log())
        return artifacts

    # ------------------------------------------------------------------
    # 1. threads/ -- JSON conversation threads
    # ------------------------------------------------------------------
    def _collect_threads(self) -> List:
        """Walk threads/ directory and collect JSON conversation files.

        Each thread is typically a subdirectory containing messages.json
        or similar JSON files with conversation data.
        Returns List[AIArtifact].
        """
        results = []  # type: List[Any]
        threads_dir = os.path.join(self._root, "threads")
        if not os.path.isdir(threads_dir):
            return results

        for dirpath, _dirnames, filenames in os.walk(threads_dir):
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

                rel_path = os.path.relpath(fpath, threads_dir)
                thread_id = os.path.basename(os.path.dirname(fpath))

                # Extract conversation details
                message_count = 0
                preview_text = ""
                model = None  # type: Optional[str]

                if isinstance(data, dict):
                    # Thread metadata file (e.g. thread.json)
                    title = data.get("title", data.get("name", ""))
                    model = data.get("model", data.get("model_id"))
                    preview_text = title if title else json.dumps(data)

                elif isinstance(data, list):
                    # Messages array
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
                    conversation_id=thread_id,
                    token_estimate=self._estimate_tokens(preview_text),
                    metadata={
                        "relative_path": rel_path,
                        "thread_id": thread_id,
                        "message_count": message_count,
                        "filename": fname,
                    },
                ))

        return results

    # ------------------------------------------------------------------
    # 2. models/ -- model configurations and inventory
    # ------------------------------------------------------------------
    def _collect_models(self) -> List:
        """Collect model inventory from models/ directory.

        Uses LocalLLMRunnerMixin._collect_model_inventory() to walk model
        files and collect metadata without reading binary content.
        Returns List[AIArtifact].
        """
        models_dir = os.path.join(self._root, "models")
        return self._collect_model_inventory(models_dir, tool_name="Jan")

    # ------------------------------------------------------------------
    # 3. logs/app.log -- application log
    # ------------------------------------------------------------------
    def _collect_app_log(self) -> List:
        """Collect the Jan application log file.

        Returns List[AIArtifact].
        """
        results = []  # type: List[Any]
        log_path = os.path.join(self._root, "logs", "app.log")
        if not os.path.isfile(log_path):
            return results
        if os.path.islink(log_path):
            return results

        fmeta = self._file_metadata(log_path)
        file_hash = self._hash_file(log_path)
        text = self._safe_read_text(log_path)

        if text is None:
            # File too large; record metadata only
            results.append(self._make_artifact(
                artifact_type="log",
                file_path=log_path,
                file_hash_sha256=file_hash,
                file_size_bytes=fmeta.get("file_size_bytes"),
                file_modified=fmeta.get("file_modified"),
                file_created=fmeta.get("file_created"),
                content_preview="Jan app log (too large to read; {} bytes)".format(
                    fmeta.get("file_size_bytes", 0),
                ),
                metadata={
                    "filename": "app.log",
                    "truncated": True,
                },
            ))
            return results

        sanitized = sanitize_content(text)

        results.append(self._make_artifact(
            artifact_type="log",
            file_path=log_path,
            file_hash_sha256=file_hash,
            file_size_bytes=fmeta.get("file_size_bytes"),
            file_modified=fmeta.get("file_modified"),
            file_created=fmeta.get("file_created"),
            content_preview=self._content_preview(sanitized),
            raw_data=sanitized if len(sanitized) < 50000 else None,
            metadata={
                "filename": "app.log",
                "log_size_bytes": len(text),
            },
        ))

        return results
