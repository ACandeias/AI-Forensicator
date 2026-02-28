"""Collector for cagent artifacts (~/.cagent/).

Cagent stores OCI container manifests with annotations in a store/ directory.
We walk the store and read JSON manifests for forensic analysis.
"""

import json
import os
from typing import Any, Dict, List, Optional

from collectors.base import AbstractCollector
from config import HOME
from normalizer import sanitize_content


class CagentCollector(AbstractCollector):
    """Collect artifacts from the cagent tool.

    Artifact root: ~/.cagent/
    Contains store/ directory with OCI container manifests and annotations.
    """

    def __init__(self) -> None:
        super().__init__()
        self._root = os.path.join(HOME, ".cagent")

    @property
    def name(self) -> str:
        return "cagent"

    def detect(self) -> bool:
        return os.path.isdir(self._root)

    def collect(self) -> List:
        artifacts = []  # type: List[Any]
        artifacts.extend(self._collect_store_manifests())
        artifacts.extend(self._collect_config_files())
        return artifacts

    # ------------------------------------------------------------------
    # 1. store/ -- OCI container manifests
    # ------------------------------------------------------------------
    def _collect_store_manifests(self) -> List:
        """Walk the store/ directory and collect JSON manifest files.
        Artifact type: container_manifest."""
        results = []  # type: List[Any]
        store_dir = os.path.join(self._root, "store")
        if not os.path.isdir(store_dir):
            return results

        manifest_count = 0
        total_layers = 0

        for dirpath, _dirnames, filenames in os.walk(store_dir):
            if os.path.islink(dirpath):
                continue
            for fname in filenames:
                fpath = os.path.join(dirpath, fname)
                if os.path.islink(fpath) or not os.path.isfile(fpath):
                    continue
                if self._is_credential_file(fpath):
                    continue

                # Try to read as JSON manifest
                data = self._safe_read_json(fpath)
                if data is None:
                    continue

                fmeta = self._file_metadata(fpath)
                file_hash = self._hash_file(fpath)

                # Extract OCI manifest fields
                media_type = ""
                annotations = {}  # type: Dict[str, Any]
                layers = []  # type: List[Any]
                config_info = {}  # type: Dict[str, Any]

                if isinstance(data, dict):
                    media_type = data.get("mediaType", "")
                    annotations = data.get("annotations", {})
                    if not isinstance(annotations, dict):
                        annotations = {}
                    layers = data.get("layers", [])
                    if not isinstance(layers, list):
                        layers = []
                    config_data = data.get("config", {})
                    if isinstance(config_data, dict):
                        config_info = {
                            "mediaType": config_data.get("mediaType", ""),
                            "digest": config_data.get("digest", ""),
                            "size": config_data.get("size", 0),
                        }

                manifest_count += 1
                total_layers += len(layers)

                # Build layer summary
                layer_summary = []
                for layer in layers:
                    if isinstance(layer, dict):
                        layer_summary.append({
                            "mediaType": layer.get("mediaType", ""),
                            "digest": layer.get("digest", ""),
                            "size": layer.get("size", 0),
                        })

                sanitized = sanitize_content(json.dumps(data))
                rel_path = os.path.relpath(fpath, store_dir)

                results.append(self._make_artifact(
                    artifact_type="container_manifest",
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
                        "media_type": media_type,
                        "annotations": annotations,
                        "layer_count": len(layers),
                        "layers": layer_summary[:20],
                        "config": config_info,
                    },
                ))

        # Insert summary artifact at the beginning if manifests were found
        if manifest_count > 0:
            results.insert(0, self._make_artifact(
                artifact_type="container_manifest",
                file_path=store_dir,
                content_preview="cagent: {} OCI manifests, {} total layers".format(
                    manifest_count, total_layers,
                ),
                metadata={
                    "manifest_count": manifest_count,
                    "total_layers": total_layers,
                },
            ))

        return results

    # ------------------------------------------------------------------
    # 2. Config files in root
    # ------------------------------------------------------------------
    def _collect_config_files(self) -> List:
        """Collect JSON/YAML config files in the cagent root.
        Artifact type: config."""
        results = []  # type: List[Any]

        try:
            entries = os.listdir(self._root)
        except OSError:
            return results

        for fname in entries:
            if not (fname.endswith(".json") or fname.endswith(".yaml") or fname.endswith(".yml")):
                continue
            fpath = os.path.join(self._root, fname)
            if os.path.islink(fpath) or not os.path.isfile(fpath):
                continue
            if self._is_credential_file(fpath):
                continue

            data = self._safe_read_json(fpath)
            if data is not None:
                preview_text = json.dumps(data)
            else:
                text = self._safe_read_text(fpath)
                if text is None:
                    continue
                preview_text = text

            fmeta = self._file_metadata(fpath)
            file_hash = self._hash_file(fpath)
            sanitized = sanitize_content(preview_text)

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

        return results
