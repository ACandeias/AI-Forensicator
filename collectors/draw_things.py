"""Draw Things artifact collector."""

import json
import os
import plistlib
from typing import Any, Dict, List

from collectors.base import AbstractCollector
from config import HOME
from normalizer import sanitize_content
from schema import AIArtifact


class DrawThingsCollector(AbstractCollector):
    """Collect artifacts from Draw Things (sandboxed macOS image generation app).

    Artifact root: ~/Library/Containers/com.liuliu.draw-things/
    NOTE: This is a sandboxed macOS app.  PermissionError is handled
    gracefully.  Collects model inventory metadata only.
    """

    def __init__(self) -> None:
        super().__init__()
        self._root = os.path.join(
            HOME, "Library", "Containers", "com.liuliu.draw-things",
        )

    @property
    def name(self) -> str:
        return "draw_things"

    def detect(self) -> bool:
        return os.path.isdir(self._root)

    def collect(self) -> List[AIArtifact]:
        if not os.path.isdir(self._root):
            return []

        artifacts = []  # type: List[AIArtifact]
        artifacts.extend(self._collect_model_inventory())
        artifacts.extend(self._collect_config_files())
        return artifacts

    # ------------------------------------------------------------------
    # 1. Model inventory (metadata only)
    # ------------------------------------------------------------------
    def _collect_model_inventory(self) -> List[AIArtifact]:
        """Inventory downloaded models by metadata only.
        Artifact type: model_inventory."""
        results = []  # type: List[AIArtifact]

        model_extensions = {
            ".ckpt", ".safetensors", ".bin", ".pt", ".pth",
            ".onnx", ".mlmodel", ".mlmodelc",
        }

        model_entries = []  # type: List[Dict[str, Any]]
        total_size = 0

        try:
            dir_walker = os.walk(self._root)
        except (OSError, PermissionError):
            return results

        for dirpath, _dirnames, filenames in dir_walker:
            if os.path.islink(dirpath):
                continue
            for fname in filenames:
                ext = os.path.splitext(fname)[1].lower()
                if ext not in model_extensions:
                    continue

                fpath = os.path.join(dirpath, fname)
                if os.path.islink(fpath) or not os.path.isfile(fpath):
                    continue

                try:
                    fmeta = self._file_metadata(fpath)
                except (OSError, PermissionError):
                    continue

                size = fmeta.get("file_size_bytes") or 0
                total_size += size

                model_entries.append({
                    "filename": fname,
                    "relative_path": os.path.relpath(fpath, self._root),
                    "size_bytes": size,
                    "modified": fmeta.get("file_modified"),
                    "created": fmeta.get("file_created"),
                    "extension": ext,
                })

        if not model_entries:
            return results

        model_entries.sort(
            key=lambda x: x.get("modified") or "",
            reverse=True,
        )

        results.append(self._make_artifact(
            artifact_type="model_inventory",
            file_path=self._root,
            content_preview="Draw Things: {} model files, {:.1f} GB total (metadata only)".format(
                len(model_entries),
                total_size / (1024 * 1024 * 1024),
            ),
            metadata={
                "model_count": len(model_entries),
                "total_size_bytes": total_size,
                "total_size_gb": round(total_size / (1024 * 1024 * 1024), 2),
                "models": model_entries[:50],
                "sandbox_container": "com.liuliu.draw-things",
                "content_note": "Metadata only -- model binaries NOT read",
            },
        ))

        return results

    # ------------------------------------------------------------------
    # 2. Configuration / preference files
    # ------------------------------------------------------------------
    def _collect_config_files(self) -> List[AIArtifact]:
        """Collect JSON and plist configuration files.
        Artifact type: config."""
        results = []  # type: List[AIArtifact]

        try:
            dir_walker = os.walk(self._root)
        except (OSError, PermissionError):
            return results

        for dirpath, _dirnames, filenames in dir_walker:
            if os.path.islink(dirpath):
                continue
            for fname in filenames:
                if not (fname.endswith(".json") or fname.endswith(".plist")):
                    continue
                fpath = os.path.join(dirpath, fname)
                if os.path.islink(fpath) or not os.path.isfile(fpath):
                    continue
                if self._is_credential_file(fpath):
                    continue

                try:
                    fmeta = self._file_metadata(fpath)
                    file_hash = self._hash_file(fpath)
                except (OSError, PermissionError):
                    continue

                if fname.endswith(".json"):
                    data = self._safe_read_json(fpath)
                    if data is None:
                        continue
                    sanitized = sanitize_content(
                        json.dumps(data, default=str)
                    )
                elif fname.endswith(".plist"):
                    try:
                        with open(fpath, "rb") as f:
                            plist_data = plistlib.load(f)
                        sanitized = sanitize_content(
                            json.dumps(
                                self._plist_to_safe(plist_data), default=str,
                            )
                        )
                    except (plistlib.InvalidFileException, OSError,
                            PermissionError, ValueError):
                        continue
                else:
                    continue

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
                        "sandbox_container": "com.liuliu.draw-things",
                    },
                ))

        return results

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _plist_to_safe(obj):
        """Convert plist data types to JSON-serializable types."""
        if isinstance(obj, dict):
            return {
                str(k): DrawThingsCollector._plist_to_safe(v)
                for k, v in obj.items()
            }
        if isinstance(obj, (list, tuple)):
            return [DrawThingsCollector._plist_to_safe(item) for item in obj]
        if isinstance(obj, bytes):
            if len(obj) <= 64:
                return "<binary:{}>".format(obj.hex())
            return "<binary:{}... ({} bytes)>".format(
                obj[:32].hex(), len(obj),
            )
        if isinstance(obj, (int, float, str, bool)):
            return obj
        return str(obj)
