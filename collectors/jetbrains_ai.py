"""JetBrains AI Assistant artifact collector."""

import json
import os
from typing import Any, Dict, List, Optional

from collectors.base import AbstractCollector
from config import HOME
from normalizer import sanitize_content
from schema import AIArtifact


# IDE product prefixes used for JetBrains cache directories
JETBRAINS_IDE_PREFIXES = [
    "IntelliJIdea",
    "PyCharm",
    "WebStorm",
    "GoLand",
    "CLion",
    "Rider",
    "PhpStorm",
    "RubyMine",
    "DataGrip",
    "DataSpell",
]


class JetBrainsAICollector(AbstractCollector):
    """Collect artifacts from JetBrains AI Assistant plugin.

    Artifact root: ~/Library/Caches/JetBrains/*/aia/
    Globs across IDE versions (IntelliJIdea*, PyCharm*, WebStorm*, etc.)
    to find AI Assistant cache directories.
    """

    def __init__(self) -> None:
        super().__init__()
        self._caches_root = os.path.join(HOME, "Library", "Caches", "JetBrains")

    @property
    def name(self) -> str:
        return "jetbrains_ai"

    def detect(self) -> bool:
        """Check if any JetBrains cache directory exists with aia/ subdirectory."""
        for aia_dir in self._find_aia_dirs():
            return True
        return False

    def collect(self) -> List[AIArtifact]:
        aia_dirs = self._find_aia_dirs()
        if not aia_dirs:
            return []

        artifacts = []  # type: List[AIArtifact]
        for aia_dir in aia_dirs:
            artifacts.extend(self._collect_aia_directory(aia_dir))
        return artifacts

    # ------------------------------------------------------------------
    # Directory discovery
    # ------------------------------------------------------------------
    def _find_aia_dirs(self) -> List[str]:
        """Find all aia/ directories across JetBrains IDE cache versions."""
        aia_dirs = []  # type: List[str]

        if not os.path.isdir(self._caches_root):
            return aia_dirs

        try:
            entries = os.listdir(self._caches_root)
        except OSError:
            return aia_dirs

        for entry in entries:
            # Check if this directory matches a known IDE prefix
            matches = False
            for prefix in JETBRAINS_IDE_PREFIXES:
                if entry.startswith(prefix):
                    matches = True
                    break

            if not matches:
                continue

            ide_dir = os.path.join(self._caches_root, entry)
            if not os.path.isdir(ide_dir) or os.path.islink(ide_dir):
                continue

            aia_dir = os.path.join(ide_dir, "aia")
            if os.path.isdir(aia_dir):
                aia_dirs.append(aia_dir)

        return aia_dirs

    # ------------------------------------------------------------------
    # Collect from a single aia/ directory
    # ------------------------------------------------------------------
    def _collect_aia_directory(self, aia_dir) -> List[AIArtifact]:
        """Collect artifacts from a single aia/ directory.
        Artifact type: ai_assistant_data."""
        results = []  # type: List[AIArtifact]

        # Determine the IDE name from the parent directory
        parent_name = os.path.basename(os.path.dirname(aia_dir))

        file_entries = []  # type: List[Dict[str, Any]]
        total_size = 0

        for dirpath, _dirnames, filenames in os.walk(aia_dir):
            if os.path.islink(dirpath):
                continue
            for fname in filenames:
                fpath = os.path.join(dirpath, fname)
                if os.path.islink(fpath) or not os.path.isfile(fpath):
                    continue
                if self._is_credential_file(fpath):
                    continue

                fmeta = self._file_metadata(fpath)
                size = fmeta.get("file_size_bytes") or 0
                total_size += size

                file_entries.append({
                    "filename": fname,
                    "relative_path": os.path.relpath(fpath, aia_dir),
                    "size_bytes": size,
                    "modified": fmeta.get("file_modified"),
                })

                # Collect JSON files content
                if fname.endswith(".json"):
                    data = self._safe_read_json(fpath)
                    if data is not None:
                        file_hash = self._hash_file(fpath)
                        sanitized = sanitize_content(
                            json.dumps(data, default=str)
                        )

                        results.append(self._make_artifact(
                            artifact_type="ai_assistant_data",
                            file_path=fpath,
                            file_hash_sha256=file_hash,
                            file_size_bytes=fmeta.get("file_size_bytes"),
                            file_modified=fmeta.get("file_modified"),
                            file_created=fmeta.get("file_created"),
                            content_preview=self._content_preview(sanitized),
                            raw_data=sanitized if len(sanitized) < 50000 else None,
                            metadata={
                                "filename": fname,
                                "ide_version_dir": parent_name,
                                "relative_path": os.path.relpath(fpath, aia_dir),
                            },
                        ))

                # Collect XML/text config files
                elif fname.endswith((".xml", ".yaml", ".yml", ".txt")):
                    text = self._safe_read_text(fpath)
                    if text is not None:
                        file_hash = self._hash_file(fpath)
                        sanitized = sanitize_content(text)

                        results.append(self._make_artifact(
                            artifact_type="ai_assistant_data",
                            file_path=fpath,
                            file_hash_sha256=file_hash,
                            file_size_bytes=fmeta.get("file_size_bytes"),
                            file_modified=fmeta.get("file_modified"),
                            file_created=fmeta.get("file_created"),
                            content_preview=self._content_preview(sanitized),
                            raw_data=sanitized if len(sanitized) < 50000 else None,
                            metadata={
                                "filename": fname,
                                "ide_version_dir": parent_name,
                                "relative_path": os.path.relpath(fpath, aia_dir),
                            },
                        ))

        # Summary artifact for this IDE version
        if file_entries:
            results.insert(0, self._make_artifact(
                artifact_type="ai_assistant_data",
                file_path=aia_dir,
                content_preview="JetBrains AI ({}): {} files, {:.1f} KB total".format(
                    parent_name, len(file_entries),
                    total_size / 1024,
                ),
                metadata={
                    "ide_version_dir": parent_name,
                    "file_count": len(file_entries),
                    "total_size_bytes": total_size,
                    "files": file_entries[:50],
                },
            ))

        return results
