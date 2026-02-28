"""Cline (Claude Dev) VS Code extension collector."""

import json
import os
from typing import List

from collectors.base import AbstractCollector
from collectors.mixins import VSCodeExtensionMixin
from config import ARTIFACT_PATHS
from normalizer import sanitize_content
from schema import AIArtifact


CLINE_EXTENSION_ID = "saoudrizwan.claude-dev"


class ClineCollector(VSCodeExtensionMixin, AbstractCollector):
    """Collect artifacts from the Cline (Claude Dev) VS Code extension.

    Collects task conversation histories, UI messages, and task history
    from globalStorage.
    """

    @property
    def name(self) -> str:
        return "cline"

    def _storage_path(self) -> str:
        return self._get_extension_storage_path(CLINE_EXTENSION_ID)

    def detect(self) -> bool:
        return os.path.isdir(self._storage_path())

    def collect(self) -> List[AIArtifact]:
        storage = self._storage_path()
        if not os.path.isdir(storage):
            return []

        results = []  # type: List[AIArtifact]

        # Collect general extension JSON/YAML files
        results.extend(self._collect_extension_json_files(storage))

        # Collect state.vscdb if present
        results.extend(self._collect_extension_state_vscdb(storage))

        # Walk tasks/ subdirectory for conversation history files
        tasks_dir = os.path.join(storage, "tasks")
        if os.path.isdir(tasks_dir):
            results.extend(self._collect_task_conversations(tasks_dir))

        return results

    def _collect_task_conversations(self, tasks_dir) -> List[AIArtifact]:
        """Walk tasks/<id>/ subdirectories for conversation JSON files.

        Looks for api_conversation_history.json and ui_messages.json
        in each task subdirectory.
        """
        results = []  # type: List[AIArtifact]
        target_files = {
            "api_conversation_history.json",
            "ui_messages.json",
        }

        try:
            task_ids = os.listdir(tasks_dir)
        except OSError:
            return results

        for task_id in task_ids:
            task_dir = os.path.join(tasks_dir, task_id)
            if not os.path.isdir(task_dir) or os.path.islink(task_dir):
                continue

            for fname in target_files:
                fpath = os.path.join(task_dir, fname)
                if not os.path.isfile(fpath) or os.path.islink(fpath):
                    continue
                if self._is_credential_file(fpath):
                    continue

                fmeta = self._file_metadata(fpath)
                file_hash = self._hash_file(fpath)

                data = self._safe_read_json(fpath)
                if data is None:
                    continue

                preview_text = json.dumps(data)
                sanitized = sanitize_content(preview_text)

                # Extract token counts if available
                token_estimate = None
                if isinstance(data, list):
                    total_tokens = 0
                    for entry in data:
                        if isinstance(entry, dict):
                            content = entry.get("content", "")
                            if isinstance(content, str):
                                total_tokens += self._estimate_tokens(content)
                    if total_tokens > 0:
                        token_estimate = total_tokens

                results.append(self._make_artifact(
                    artifact_type="conversation_history",
                    file_path=fpath,
                    file_hash_sha256=file_hash,
                    file_size_bytes=fmeta.get("file_size_bytes"),
                    file_modified=fmeta.get("file_modified"),
                    file_created=fmeta.get("file_created"),
                    content_preview=self._content_preview(sanitized),
                    raw_data=sanitized if len(sanitized) < 50000 else None,
                    conversation_id=task_id,
                    token_estimate=token_estimate,
                    metadata={
                        "filename": fname,
                        "task_id": task_id,
                        "entry_count": len(data) if isinstance(data, list) else 0,
                    },
                ))

        return results
