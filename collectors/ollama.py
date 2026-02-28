"""Ollama local LLM runner artifact collector (~/.ollama/)."""

import json
import os
from typing import Any, Dict, List, Optional

from collectors.base import AbstractCollector
from collectors.mixins import LocalLLMRunnerMixin
from config import HOME
from normalizer import sanitize_content
from schema import AIArtifact


class OllamaCollector(LocalLLMRunnerMixin, AbstractCollector):
    """Collect artifacts from the Ollama local LLM runner.

    Artifact root: ~/.ollama/
    Collects model manifests and config files.
    Does NOT read blob content from models/blobs/.
    """

    def __init__(self) -> None:
        super().__init__()
        self._root = os.path.join(HOME, ".ollama")

    @property
    def name(self) -> str:
        return "ollama"

    def detect(self) -> bool:
        return os.path.exists(self._root)

    def collect(self) -> List[AIArtifact]:
        artifacts = []  # type: List[Any]
        artifacts.extend(self._collect_manifests())
        artifacts.extend(self._collect_config_files())
        return artifacts

    # ------------------------------------------------------------------
    # 1. models/manifests/ -- model names, digests, sizes
    # ------------------------------------------------------------------
    def _collect_manifests(self) -> List:
        """Collect model manifest files from models/manifests/.

        Uses LocalLLMRunnerMixin._collect_model_manifests() to extract
        model names, digests, and sizes without reading blob content.
        Returns List[AIArtifact].
        """
        manifests_dir = os.path.join(self._root, "models", "manifests")
        return self._collect_model_manifests(manifests_dir, tool_name="Ollama")

    # ------------------------------------------------------------------
    # 2. Config files -- Modelfile, etc.
    # ------------------------------------------------------------------
    def _collect_config_files(self) -> List:
        """Collect configuration files from the Ollama root directory.

        Looks for known config files (JSON, YAML, text) at the top level.
        Skips symlinks and credential files.
        Returns List[AIArtifact].
        """
        results = []  # type: List[Any]
        if not os.path.isdir(self._root):
            return results

        config_extensions = (".json", ".yaml", ".yml", ".conf", ".cfg")

        try:
            entries = os.listdir(self._root)
        except OSError:
            return results

        for fname in entries:
            fpath = os.path.join(self._root, fname)
            if os.path.islink(fpath):
                continue
            if not os.path.isfile(fpath):
                continue
            if self._is_credential_file(fpath):
                continue

            # Only collect known config file types
            if not fname.endswith(config_extensions):
                continue

            fmeta = self._file_metadata(fpath)
            file_hash = self._hash_file(fpath)

            data = self._safe_read_json(fpath)
            if data is not None:
                preview_text = sanitize_content(json.dumps(data))
            else:
                text = self._safe_read_text(fpath)
                preview_text = sanitize_content(text or "")

            results.append(self._make_artifact(
                artifact_type="config",
                file_path=fpath,
                file_hash_sha256=file_hash,
                file_size_bytes=fmeta.get("file_size_bytes"),
                file_modified=fmeta.get("file_modified"),
                file_created=fmeta.get("file_created"),
                content_preview=self._content_preview(preview_text),
                raw_data=preview_text if len(preview_text) < 50000 else None,
                metadata={
                    "filename": fname,
                },
            ))

        return results
