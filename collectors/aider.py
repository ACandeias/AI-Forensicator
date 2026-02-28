"""Collector for Aider AI pair-programming tool artifacts.

Paths:
  ~/.aider/                      -- aider data directory
  ~/.aider.chat.history.md       -- chat transcript in home directory
  ~/.aider.conf.yml              -- global config in home directory
"""

import os
from typing import Any, List, Optional

from collectors.base import AbstractCollector
from config import HOME
from normalizer import sanitize_content


class AiderCollector(AbstractCollector):
    """Collect artifacts from the Aider CLI coding assistant.

    Aider stores chat history as Markdown transcripts and config as YAML.
    History files (.aider.chat.history.md) live in the user's home directory
    and also in individual project directories.
    """

    def __init__(self) -> None:
        super().__init__()
        self._aider_dir = os.path.join(HOME, ".aider")
        self._home_history = os.path.join(HOME, ".aider.chat.history.md")
        self._home_config = os.path.join(HOME, ".aider.conf.yml")

    @property
    def name(self) -> str:
        return "aider"

    def detect(self) -> bool:
        return (
            os.path.isdir(self._aider_dir)
            or os.path.isfile(self._home_history)
            or os.path.isfile(self._home_config)
        )

    def collect(self) -> List:
        artifacts = []  # type: List[Any]
        artifacts.extend(self._collect_chat_history())
        artifacts.extend(self._collect_config())
        artifacts.extend(self._collect_aider_dir())
        return artifacts

    # ------------------------------------------------------------------
    # 1. .aider.chat.history.md -- Markdown chat transcripts
    # ------------------------------------------------------------------
    def _collect_chat_history(self) -> List:
        """Collect .aider.chat.history.md files from the home directory
        and common project directories.  Artifact type: conversation."""
        results = []  # type: List[Any]

        # Check the home directory history file
        if os.path.isfile(self._home_history) and not os.path.islink(self._home_history):
            results.extend(self._parse_history_file(self._home_history))

        # Also scan common project directories under home for aider history files
        common_dirs = [
            os.path.join(HOME, "Projects"),
            os.path.join(HOME, "projects"),
            os.path.join(HOME, "src"),
            os.path.join(HOME, "dev"),
            os.path.join(HOME, "code"),
            os.path.join(HOME, "repos"),
            os.path.join(HOME, "workspace"),
            os.path.join(HOME, "Documents"),
            os.path.join(HOME, "Desktop"),
        ]

        for project_root in common_dirs:
            if not os.path.isdir(project_root):
                continue
            try:
                for entry in os.listdir(project_root):
                    project_dir = os.path.join(project_root, entry)
                    if not os.path.isdir(project_dir) or os.path.islink(project_dir):
                        continue
                    history_path = os.path.join(
                        project_dir, ".aider.chat.history.md",
                    )
                    if os.path.isfile(history_path) and not os.path.islink(history_path):
                        results.extend(self._parse_history_file(history_path))
            except OSError:
                continue

        return results

    def _parse_history_file(self, fpath: str) -> List:
        """Parse a single .aider.chat.history.md file.
        Artifact type: conversation."""
        results = []  # type: List[Any]
        text = self._safe_read_text(fpath)
        if text is None:
            return results

        fmeta = self._file_metadata(fpath)
        file_hash = self._hash_file(fpath)

        sanitized = sanitize_content(text)

        results.append(self._make_artifact(
            artifact_type="conversation",
            file_path=fpath,
            file_hash_sha256=file_hash,
            file_size_bytes=fmeta.get("file_size_bytes"),
            file_modified=fmeta.get("file_modified"),
            file_created=fmeta.get("file_created"),
            content_preview=self._content_preview(sanitized),
            token_estimate=self._estimate_tokens(text),
            metadata={
                "format": "markdown_transcript",
                "transcript_length_chars": len(text),
                "source_directory": os.path.dirname(fpath),
            },
        ))

        return results

    # ------------------------------------------------------------------
    # 2. .aider.conf.yml -- global configuration
    # ------------------------------------------------------------------
    def _collect_config(self) -> List:
        """Collect .aider.conf.yml from the home directory and
        ~/.aider/ directory.  Artifact type: config."""
        results = []  # type: List[Any]

        config_paths = [
            self._home_config,
            os.path.join(self._aider_dir, ".aider.conf.yml"),
        ]

        for path in config_paths:
            if not os.path.isfile(path) or os.path.islink(path):
                continue

            fmeta = self._file_metadata(path)
            file_hash = self._hash_file(path)

            raw_text = self._safe_read_text(path)
            if raw_text is None:
                continue

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
    # 3. ~/.aider/ directory -- caches, logs, and data
    # ------------------------------------------------------------------
    def _collect_aider_dir(self) -> List:
        """Walk the ~/.aider/ directory for data files.
        Artifact type: analytics."""
        results = []  # type: List[Any]
        if not os.path.isdir(self._aider_dir):
            return results

        for dirpath, _dirnames, filenames in os.walk(self._aider_dir):
            if os.path.islink(dirpath):
                continue
            for fname in filenames:
                fpath = os.path.join(dirpath, fname)
                if os.path.islink(fpath) or not os.path.isfile(fpath):
                    continue
                if self._is_credential_file(fpath):
                    continue

                # Collect JSON, YAML, Markdown, and text files
                if not (fname.endswith(".json") or fname.endswith(".yaml")
                        or fname.endswith(".yml") or fname.endswith(".md")
                        or fname.endswith(".txt") or fname.endswith(".log")):
                    continue

                fmeta = self._file_metadata(fpath)
                file_hash = self._hash_file(fpath)

                raw_text = self._safe_read_text(fpath)
                if raw_text is None:
                    continue

                sanitized = sanitize_content(raw_text)

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
                        "relative_path": os.path.relpath(fpath, self._aider_dir),
                    },
                ))

        return results
