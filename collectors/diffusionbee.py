"""DiffusionBee artifact collector."""

import json
import os
from typing import Any, Dict, List

from collectors.base import AbstractCollector
from config import HOME
from normalizer import sanitize_content
from schema import AIArtifact


class DiffusionBeeCollector(AbstractCollector):
    """Collect artifacts from DiffusionBee (local Stable Diffusion GUI).

    Artifact root: ~/.diffusionbee/
    Collects generated image inventory (METADATA ONLY -- file names, sizes,
    timestamps, NOT image content), model list, and generation configs.
    """

    def __init__(self) -> None:
        super().__init__()
        self._root = os.path.join(HOME, ".diffusionbee")

    @property
    def name(self) -> str:
        return "diffusionbee"

    def detect(self) -> bool:
        return os.path.isdir(self._root)

    def collect(self) -> List[AIArtifact]:
        if not os.path.isdir(self._root):
            return []

        artifacts = []  # type: List[AIArtifact]
        artifacts.extend(self._collect_image_inventory())
        artifacts.extend(self._collect_model_list())
        artifacts.extend(self._collect_generation_configs())
        return artifacts

    # ------------------------------------------------------------------
    # 1. Generated image inventory (metadata only)
    # ------------------------------------------------------------------
    def _collect_image_inventory(self) -> List[AIArtifact]:
        """Inventory generated images by metadata only (names, sizes,
        timestamps).  Does NOT read image content.
        Artifact type: generated_image_inventory."""
        results = []  # type: List[AIArtifact]

        images_dir = os.path.join(self._root, "images")
        if not os.path.isdir(images_dir):
            # Also check for output directory
            images_dir = self._root
            # Fall through and scan for image files in the root

        image_extensions = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff"}
        image_entries = []  # type: List[Dict[str, Any]]
        total_size = 0

        for dirpath, _dirnames, filenames in os.walk(self._root):
            if os.path.islink(dirpath):
                continue
            for fname in filenames:
                ext = os.path.splitext(fname)[1].lower()
                if ext not in image_extensions:
                    continue
                fpath = os.path.join(dirpath, fname)
                if os.path.islink(fpath) or not os.path.isfile(fpath):
                    continue

                fmeta = self._file_metadata(fpath)
                size = fmeta.get("file_size_bytes") or 0
                total_size += size

                image_entries.append({
                    "filename": fname,
                    "relative_path": os.path.relpath(fpath, self._root),
                    "size_bytes": size,
                    "modified": fmeta.get("file_modified"),
                    "created": fmeta.get("file_created"),
                })

        if not image_entries:
            return results

        image_entries.sort(
            key=lambda x: x.get("modified") or "",
            reverse=True,
        )

        results.append(self._make_artifact(
            artifact_type="generated_image_inventory",
            file_path=self._root,
            content_preview="DiffusionBee: {} generated images, {:.1f} MB total (metadata only)".format(
                len(image_entries),
                total_size / (1024 * 1024),
            ),
            metadata={
                "image_count": len(image_entries),
                "total_size_bytes": total_size,
                "total_size_mb": round(total_size / (1024 * 1024), 2),
                "newest_image": image_entries[0] if image_entries else None,
                "oldest_image": image_entries[-1] if image_entries else None,
                "content_note": "Metadata only -- image content NOT extracted",
            },
        ))

        return results

    # ------------------------------------------------------------------
    # 2. Model list
    # ------------------------------------------------------------------
    def _collect_model_list(self) -> List[AIArtifact]:
        """Inventory downloaded models.
        Artifact type: model_inventory."""
        results = []  # type: List[AIArtifact]

        models_dir = os.path.join(self._root, "models")
        if not os.path.isdir(models_dir):
            return results

        model_entries = []  # type: List[Dict[str, Any]]
        total_size = 0

        for dirpath, _dirnames, filenames in os.walk(models_dir):
            if os.path.islink(dirpath):
                continue
            for fname in filenames:
                fpath = os.path.join(dirpath, fname)
                if os.path.islink(fpath) or not os.path.isfile(fpath):
                    continue

                fmeta = self._file_metadata(fpath)
                size = fmeta.get("file_size_bytes") or 0
                total_size += size

                model_entries.append({
                    "filename": fname,
                    "relative_path": os.path.relpath(fpath, models_dir),
                    "size_bytes": size,
                    "modified": fmeta.get("file_modified"),
                })

        if not model_entries:
            return results

        results.append(self._make_artifact(
            artifact_type="model_inventory",
            file_path=models_dir,
            content_preview="DiffusionBee: {} model files, {:.1f} GB total".format(
                len(model_entries),
                total_size / (1024 * 1024 * 1024),
            ),
            metadata={
                "model_count": len(model_entries),
                "total_size_bytes": total_size,
                "total_size_gb": round(total_size / (1024 * 1024 * 1024), 2),
                "models": model_entries[:50],
            },
        ))

        return results

    # ------------------------------------------------------------------
    # 3. Generation configs
    # ------------------------------------------------------------------
    def _collect_generation_configs(self) -> List[AIArtifact]:
        """Collect generation configuration / history JSON files.
        Artifact type: generation_config."""
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

                results.append(self._make_artifact(
                    artifact_type="generation_config",
                    file_path=fpath,
                    file_hash_sha256=file_hash,
                    file_size_bytes=fmeta.get("file_size_bytes"),
                    file_modified=fmeta.get("file_modified"),
                    file_created=fmeta.get("file_created"),
                    content_preview=self._content_preview(sanitized),
                    raw_data=sanitized if len(sanitized) < 50000 else None,
                    metadata={
                        "filename": fname,
                    },
                ))

        return results
