"""GPT4All local LLM runner artifact collector (~/.local/share/nomic.ai/GPT4All/)."""

import json
import os
from typing import Any, Dict, List, Optional

from collectors.base import AbstractCollector
from collectors.mixins import LocalLLMRunnerMixin
from config import HOME
from normalizer import sanitize_content, estimate_model_from_content
from schema import AIArtifact


class GPT4AllCollector(LocalLLMRunnerMixin, AbstractCollector):
    """Collect artifacts from the GPT4All local LLM runner.

    Artifact root: ~/.local/share/nomic.ai/GPT4All/
    Collects chat history, LocalDocs embeddings metadata, and model inventory.
    Does NOT read binary model files.
    """

    def __init__(self) -> None:
        super().__init__()
        self._root = os.path.join(
            HOME, ".local", "share", "nomic.ai", "GPT4All",
        )

    @property
    def name(self) -> str:
        return "gpt4all"

    def detect(self) -> bool:
        return os.path.exists(self._root)

    def collect(self) -> List[AIArtifact]:
        artifacts = []  # type: List[Any]
        artifacts.extend(self._collect_chat_history())
        artifacts.extend(self._collect_localdocs_metadata())
        artifacts.extend(self._collect_models())
        return artifacts

    # ------------------------------------------------------------------
    # 1. Chat history -- SQLite database or JSON chat files
    # ------------------------------------------------------------------
    def _collect_chat_history(self) -> List:
        """Collect chat history from GPT4All.

        GPT4All stores chat history in a SQLite database (chat.sqlite)
        or JSON files.  Checks both patterns.
        Returns List[AIArtifact].
        """
        results = []  # type: List[Any]

        # Check for SQLite chat database
        db_path = os.path.join(self._root, "chat.sqlite")
        if os.path.isfile(db_path) and not os.path.islink(db_path):
            results.extend(self._collect_chat_db(db_path))

        # Also check for JSON chat files in chats/ directory
        chats_dir = os.path.join(self._root, "chats")
        if os.path.isdir(chats_dir):
            results.extend(self._collect_chat_json_files(chats_dir))

        return results

    def _collect_chat_db(self, db_path) -> List:
        """Query the GPT4All chat SQLite database.

        Returns List[AIArtifact].
        """
        results = []  # type: List[Any]
        fmeta = self._file_metadata(db_path)
        file_hash = self._hash_file(db_path)

        # Try querying common table structures
        for table_query in [
            "SELECT * FROM conversations ORDER BY rowid DESC",
            "SELECT * FROM chats ORDER BY rowid DESC",
            "SELECT * FROM messages ORDER BY rowid DESC",
        ]:
            rows = self._safe_sqlite_read(db_path, table_query)
            if not rows:
                continue

            for row in rows:
                content = row.get("content", row.get("text", row.get("message", "")))
                role = row.get("role", row.get("type"))
                model = row.get("model", row.get("model_id"))
                conversation_id = str(
                    row.get("conversation_id", row.get("chat_id", row.get("id", "")))
                )

                content_text = str(content) if content else ""
                if not model and content_text:
                    model = estimate_model_from_content(content_text)

                sanitized = sanitize_content(content_text)

                results.append(self._make_artifact(
                    artifact_type="conversation_message",
                    file_path=db_path,
                    file_hash_sha256=file_hash,
                    file_size_bytes=fmeta.get("file_size_bytes"),
                    file_modified=fmeta.get("file_modified"),
                    file_created=fmeta.get("file_created"),
                    content_preview=self._content_preview(sanitized),
                    message_role=str(role) if role else None,
                    model_identified=model,
                    conversation_id=conversation_id if conversation_id else None,
                    token_estimate=self._estimate_tokens(content_text),
                    metadata={
                        "source_table": table_query.split("FROM ")[1].split(" ")[0],
                    },
                ))

            # Found data in this table; no need to try others
            break

        # If no row-level data, create a summary artifact for the database
        if not results:
            results.append(self._make_artifact(
                artifact_type="chat_database",
                file_path=db_path,
                file_hash_sha256=file_hash,
                file_size_bytes=fmeta.get("file_size_bytes"),
                file_modified=fmeta.get("file_modified"),
                file_created=fmeta.get("file_created"),
                content_preview="GPT4All chat database: {}".format(db_path),
                metadata={
                    "filename": os.path.basename(db_path),
                },
            ))

        return results

    def _collect_chat_json_files(self, chats_dir) -> List:
        """Walk chats/ directory for JSON conversation files.

        Returns List[AIArtifact].
        """
        results = []  # type: List[Any]

        for dirpath, _dirnames, filenames in os.walk(chats_dir):
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

                preview_text = ""
                model = None  # type: Optional[str]
                message_count = 0

                if isinstance(data, dict):
                    title = data.get("title", data.get("name", ""))
                    model = data.get("model")
                    messages = data.get("messages", data.get("conversation", []))
                    if isinstance(messages, list):
                        message_count = len(messages)
                    preview_text = title if title else json.dumps(data)

                elif isinstance(data, list):
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
                rel_path = os.path.relpath(fpath, chats_dir)

                results.append(self._make_artifact(
                    artifact_type="conversation",
                    file_path=fpath,
                    file_hash_sha256=file_hash,
                    file_size_bytes=fmeta.get("file_size_bytes"),
                    file_modified=fmeta.get("file_modified"),
                    file_created=fmeta.get("file_created"),
                    content_preview=self._content_preview(sanitized),
                    model_identified=model,
                    token_estimate=self._estimate_tokens(preview_text),
                    metadata={
                        "filename": fname,
                        "relative_path": rel_path,
                        "message_count": message_count,
                    },
                ))

        return results

    # ------------------------------------------------------------------
    # 2. LocalDocs embeddings metadata
    # ------------------------------------------------------------------
    def _collect_localdocs_metadata(self) -> List:
        """Collect LocalDocs embeddings metadata.

        GPT4All's LocalDocs feature creates embeddings for local documents.
        Collects metadata about embedded document collections without
        reading binary embedding data.
        Returns List[AIArtifact].
        """
        results = []  # type: List[Any]

        # Check for LocalDocs database
        localdocs_dir = os.path.join(self._root, "LocalDocs")
        if not os.path.isdir(localdocs_dir):
            return results

        # Walk for metadata files (JSON, SQLite) -- skip binary embeddings
        doc_entries = []
        total_size = 0

        for dirpath, _dirnames, filenames in os.walk(localdocs_dir):
            if os.path.islink(dirpath):
                continue
            for fname in filenames:
                fpath = os.path.join(dirpath, fname)
                if os.path.islink(fpath) or not os.path.isfile(fpath):
                    continue

                fmeta = self._file_metadata(fpath)
                size = fmeta.get("file_size_bytes") or 0
                total_size += size

                rel_path = os.path.relpath(fpath, localdocs_dir)

                entry = {
                    "filename": fname,
                    "relative_path": rel_path,
                    "size_bytes": size,
                    "modified": fmeta.get("file_modified"),
                }

                doc_entries.append(entry)

                # Collect JSON metadata files
                if fname.endswith(".json"):
                    data = self._safe_read_json(fpath)
                    if data is not None:
                        sanitized = sanitize_content(json.dumps(data))
                        results.append(self._make_artifact(
                            artifact_type="localdocs_config",
                            file_path=fpath,
                            file_hash_sha256=self._hash_file(fpath),
                            file_size_bytes=size,
                            file_modified=fmeta.get("file_modified"),
                            file_created=fmeta.get("file_created"),
                            content_preview=self._content_preview(sanitized),
                            raw_data=sanitized if len(sanitized) < 50000 else None,
                            metadata={
                                "filename": fname,
                                "relative_path": rel_path,
                            },
                        ))

        if doc_entries:
            results.insert(0, self._make_artifact(
                artifact_type="localdocs_inventory",
                file_path=localdocs_dir,
                content_preview="GPT4All LocalDocs: {} files, {:.1f} MB total".format(
                    len(doc_entries),
                    total_size / (1024 * 1024),
                ),
                metadata={
                    "total_files": len(doc_entries),
                    "total_size_bytes": total_size,
                    "total_size_mb": round(total_size / (1024 * 1024), 2),
                    "files": doc_entries[:100],
                },
            ))

        return results

    # ------------------------------------------------------------------
    # 3. Model inventory
    # ------------------------------------------------------------------
    def _collect_models(self) -> List:
        """Collect model inventory from the GPT4All root directory.

        Uses LocalLLMRunnerMixin._collect_model_inventory() to walk model
        files and collect metadata without reading binary content.
        Returns List[AIArtifact].
        """
        # GPT4All stores models directly in the root or in a models/ subdir
        models_dir = os.path.join(self._root, "models")
        if os.path.isdir(models_dir):
            return self._collect_model_inventory(models_dir, tool_name="GPT4All")

        # Fall back to scanning the root for model files
        return self._collect_model_inventory(self._root, tool_name="GPT4All")
