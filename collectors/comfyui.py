"""ComfyUI artifact collector."""

import json
import os
from typing import Any, List

from collectors.base import AbstractCollector
from config import HOME
from normalizer import sanitize_content
from schema import AIArtifact


class ComfyUICollector(AbstractCollector):
    """Collect artifacts from ComfyUI (Stable Diffusion node-based UI).

    Artifact root: ~/Library/Application Support/ComfyUI/
    Collects workflow JSON files and model configuration YAML files.
    """

    def __init__(self) -> None:
        super().__init__()
        self._root = os.path.join(
            HOME, "Library", "Application Support", "ComfyUI",
        )

    @property
    def name(self) -> str:
        return "comfyui"

    def detect(self) -> bool:
        return os.path.isdir(self._root)

    def collect(self) -> List[AIArtifact]:
        if not os.path.isdir(self._root):
            return []

        artifacts = []  # type: List[AIArtifact]
        artifacts.extend(self._collect_workflow_files())
        artifacts.extend(self._collect_model_configs())
        return artifacts

    # ------------------------------------------------------------------
    # 1. Workflow JSON files
    # ------------------------------------------------------------------
    def _collect_workflow_files(self) -> List[AIArtifact]:
        """Collect workflow definition JSON files.
        Artifact type: workflow."""
        results = []  # type: List[AIArtifact]

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

                data = self._safe_read_json(fpath)
                if data is None:
                    continue

                fmeta = self._file_metadata(fpath)
                file_hash = self._hash_file(fpath)
                sanitized = sanitize_content(json.dumps(data, default=str))

                # Detect workflow files by common ComfyUI keys
                node_count = 0
                if isinstance(data, dict):
                    # ComfyUI workflows have nodes as top-level numbered keys
                    # or a "nodes" list
                    nodes = data.get("nodes", [])
                    if isinstance(nodes, list):
                        node_count = len(nodes)
                    elif all(k.isdigit() for k in data.keys() if k.isdigit()):
                        node_count = len(
                            [k for k in data.keys() if k.isdigit()]
                        )

                results.append(self._make_artifact(
                    artifact_type="workflow",
                    file_path=fpath,
                    file_hash_sha256=file_hash,
                    file_size_bytes=fmeta.get("file_size_bytes"),
                    file_modified=fmeta.get("file_modified"),
                    file_created=fmeta.get("file_created"),
                    content_preview=self._content_preview(sanitized),
                    raw_data=sanitized if len(sanitized) < 50000 else None,
                    metadata={
                        "filename": fname,
                        "node_count": node_count,
                        "relative_path": os.path.relpath(fpath, self._root),
                    },
                ))

        return results

    # ------------------------------------------------------------------
    # 2. Model configuration YAML files
    # ------------------------------------------------------------------
    def _collect_model_configs(self) -> List[AIArtifact]:
        """Collect model configuration YAML files.
        Artifact type: model_config."""
        results = []  # type: List[AIArtifact]

        for dirpath, _dirnames, filenames in os.walk(self._root):
            if os.path.islink(dirpath):
                continue
            for fname in filenames:
                if not (fname.endswith(".yaml") or fname.endswith(".yml")):
                    continue
                fpath = os.path.join(dirpath, fname)
                if os.path.islink(fpath) or not os.path.isfile(fpath):
                    continue
                if self._is_credential_file(fpath):
                    continue

                text = self._safe_read_text(fpath)
                if text is None:
                    continue

                fmeta = self._file_metadata(fpath)
                file_hash = self._hash_file(fpath)
                sanitized = sanitize_content(text)

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
                        "relative_path": os.path.relpath(fpath, self._root),
                    },
                ))

        return results
