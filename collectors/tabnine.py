"""TabNine collector for standalone application artifacts."""

import json
import os
from typing import List

from collectors.base import AbstractCollector
from config import HOME
from normalizer import sanitize_content
from schema import AIArtifact


TABNINE_PATH = os.path.join(HOME, "Library", "Application Support", "TabNine")


class TabnineCollector(AbstractCollector):
    """Collect artifacts from the TabNine application directory.

    TabNine stores its data under ~/Library/Application Support/TabNine/
    rather than as a VS Code extension globalStorage entry.  This collector
    walks the directory for JSON and log files.
    """

    @property
    def name(self) -> str:
        return "tabnine"

    def detect(self) -> bool:
        return os.path.isdir(TABNINE_PATH)

    def collect(self) -> List[AIArtifact]:
        if not os.path.isdir(TABNINE_PATH):
            return []

        results = []  # type: List[AIArtifact]
        collectible_extensions = (".json", ".log", ".yaml", ".yml")

        for dirpath, _dirnames, filenames in os.walk(TABNINE_PATH):
            if os.path.islink(dirpath):
                continue
            for fname in filenames:
                if not fname.endswith(collectible_extensions):
                    continue
                fpath = os.path.join(dirpath, fname)
                if os.path.islink(fpath) or not os.path.isfile(fpath):
                    continue
                if self._is_credential_file(fpath):
                    continue

                fmeta = self._file_metadata(fpath)
                file_hash = self._hash_file(fpath)

                # Try JSON first, fall back to plain text
                data = self._safe_read_json(fpath)
                if data is not None:
                    preview_text = json.dumps(data)
                else:
                    text = self._safe_read_text(fpath)
                    preview_text = text or ""

                sanitized = sanitize_content(preview_text)
                rel_path = os.path.relpath(fpath, TABNINE_PATH)

                artifact_type = "log_file" if fname.endswith(".log") else "extension_data"

                results.append(self._make_artifact(
                    artifact_type=artifact_type,
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
