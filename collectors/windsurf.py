"""Collector for Windsurf IDE artifacts (Electron-based VS Code fork).

Paths:
  ~/Library/Application Support/Windsurf/
  ~/.codeium/
"""

import json
import os
from typing import Any, Dict, List, Optional

from collectors.base import AbstractCollector
from collectors.mixins import ElectronAppMixin
from config import HOME
from normalizer import sanitize_content, estimate_model_from_content


class WindsurfCollector(ElectronAppMixin, AbstractCollector):
    """Collect artifacts from the Windsurf IDE (Codeium Electron app).

    Windsurf is a VS Code fork by Codeium with Cascade AI assistant.
    Primary data: state.vscdb (SQLite), Session Storage, Local Storage.
    """

    def __init__(self) -> None:
        super().__init__()
        self._app_root = os.path.join(
            HOME, "Library", "Application Support", "Windsurf",
        )
        self._codeium_root = os.path.join(HOME, ".codeium")

    @property
    def name(self) -> str:
        return "windsurf"

    def detect(self) -> bool:
        return os.path.isdir(self._app_root) or os.path.isdir(self._codeium_root)

    def collect(self) -> List:
        artifacts = []  # type: List[Any]
        artifacts.extend(self._collect_state_db())
        artifacts.extend(self._collect_cascade_history())
        artifacts.extend(self._collect_session_storage())
        artifacts.extend(self._collect_local_storage())
        artifacts.extend(self._collect_codeium_config())
        return artifacts

    # ------------------------------------------------------------------
    # Locate state.vscdb
    # ------------------------------------------------------------------
    def _get_state_db_path(self) -> Optional[str]:
        """Locate state.vscdb in the User/globalStorage directory."""
        path = os.path.join(
            self._app_root, "User", "globalStorage", "state.vscdb",
        )
        if os.path.isfile(path):
            return path
        return None

    # ------------------------------------------------------------------
    # 1. state.vscdb -- key-value store (like Cursor)
    # ------------------------------------------------------------------
    def _collect_state_db(self) -> List:
        """Query state.vscdb ItemTable for Windsurf/Cascade related keys.
        Artifact type: extension_data."""
        results = []  # type: List[Any]
        db_path = self._get_state_db_path()
        if db_path is None:
            return results

        fmeta = self._file_metadata(db_path)
        file_hash = self._hash_file(db_path)

        rows = self._safe_sqlite_read(
            db_path,
            "SELECT key, value FROM ItemTable",
        )

        for row in rows:
            key = row.get("key", "")
            raw_value = row.get("value", "")

            # Skip credential-like keys
            key_lower = key.lower()
            if any(s in key_lower for s in ("token", "auth", "cookie",
                                             "session", "password",
                                             "secret", "credential",
                                             "oauth")):
                continue

            sanitized = sanitize_content(
                str(raw_value)[:10000],
            ) if raw_value else ""

            results.append(self._make_artifact(
                artifact_type="extension_data",
                file_path=db_path,
                file_hash_sha256=file_hash,
                file_size_bytes=fmeta.get("file_size_bytes"),
                file_modified=fmeta.get("file_modified"),
                file_created=fmeta.get("file_created"),
                content_preview=self._content_preview(sanitized),
                metadata={
                    "db_key": key,
                    "value_size_bytes": len(raw_value) if raw_value else 0,
                },
            ))

        return results

    # ------------------------------------------------------------------
    # 2. Cascade conversation history (cursorDiskKV equivalent)
    # ------------------------------------------------------------------
    def _collect_cascade_history(self) -> List:
        """Query state.vscdb cursorDiskKV table for Cascade/composer data.
        Windsurf reuses Cursor's table structure in some builds.
        Artifact type: conversation."""
        results = []  # type: List[Any]
        db_path = self._get_state_db_path()
        if db_path is None:
            return results

        fmeta = self._file_metadata(db_path)
        file_hash = self._hash_file(db_path)

        # Windsurf may use cursorDiskKV or a similar table for Cascade chats
        for table_name in ("cursorDiskKV",):
            rows = self._safe_sqlite_read(
                db_path,
                "SELECT key, value FROM \"{}\" WHERE key LIKE 'composerData:%'".format(
                    table_name,
                ),
            )

            for row in rows:
                key = row.get("key", "")
                raw_value = row.get("value", "")

                composer_id = key.replace("composerData:", "", 1) if key.startswith("composerData:") else key

                parsed = None  # type: Optional[Dict[str, Any]]
                try:
                    if raw_value:
                        parsed = json.loads(raw_value)
                except (json.JSONDecodeError, ValueError, TypeError):
                    pass

                preview_text = ""
                model = None  # type: Optional[str]
                message_count = 0

                if isinstance(parsed, dict):
                    messages = parsed.get("conversation", parsed.get("messages", []))
                    if isinstance(messages, list):
                        message_count = len(messages)
                        for msg in messages[:3]:
                            if isinstance(msg, dict):
                                text = msg.get("text", msg.get("content", ""))
                                if text:
                                    preview_text += str(text) + " "

                    model = parsed.get("model", parsed.get("modelId"))
                    if not model and preview_text:
                        model = estimate_model_from_content(preview_text)

                    title = parsed.get("name", parsed.get("title", ""))
                    if title:
                        preview_text = "[{}] {}".format(title, preview_text)
                elif raw_value:
                    preview_text = str(raw_value)
                    model = estimate_model_from_content(preview_text)

                results.append(self._make_artifact(
                    artifact_type="conversation",
                    file_path=db_path,
                    file_hash_sha256=file_hash,
                    file_size_bytes=fmeta.get("file_size_bytes"),
                    file_modified=fmeta.get("file_modified"),
                    file_created=fmeta.get("file_created"),
                    content_preview=self._content_preview(preview_text.strip()),
                    model_identified=model,
                    conversation_id=composer_id,
                    token_estimate=self._estimate_tokens(raw_value or ""),
                    metadata={
                        "db_key": key,
                        "composer_id": composer_id,
                        "message_count": message_count,
                        "value_size_bytes": len(raw_value) if raw_value else 0,
                    },
                ))

        return results

    # ------------------------------------------------------------------
    # 3. Session Storage (LevelDB via ElectronAppMixin)
    # ------------------------------------------------------------------
    def _collect_session_storage(self) -> List:
        """Collect Session Storage LevelDB strings from the Windsurf app."""
        results = []  # type: List[Any]
        if os.path.isdir(self._app_root):
            results.extend(self._collect_electron_session_storage(self._app_root))
        return results

    # ------------------------------------------------------------------
    # 4. Local Storage (LevelDB via ElectronAppMixin)
    # ------------------------------------------------------------------
    def _collect_local_storage(self) -> List:
        """Collect Local Storage LevelDB strings from the Windsurf app."""
        results = []  # type: List[Any]
        if os.path.isdir(self._app_root):
            results.extend(self._collect_electron_local_storage(self._app_root))
        return results

    # ------------------------------------------------------------------
    # 5. ~/.codeium/ config and data
    # ------------------------------------------------------------------
    def _collect_codeium_config(self) -> List:
        """Walk ~/.codeium/ for config and data files.
        Artifact type: config."""
        results = []  # type: List[Any]
        if not os.path.isdir(self._codeium_root):
            return results

        for dirpath, _dirnames, filenames in os.walk(self._codeium_root):
            if os.path.islink(dirpath):
                continue
            for fname in filenames:
                if not (fname.endswith(".json") or fname.endswith(".yaml")
                        or fname.endswith(".yml") or fname.endswith(".toml")):
                    continue
                fpath = os.path.join(dirpath, fname)
                if os.path.islink(fpath) or not os.path.isfile(fpath):
                    continue
                if self._is_credential_file(fpath):
                    continue

                fmeta = self._file_metadata(fpath)
                file_hash = self._hash_file(fpath)

                data = self._safe_read_json(fpath)
                if data is not None:
                    preview_text = json.dumps(data)
                else:
                    text = self._safe_read_text(fpath)
                    preview_text = text or ""

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
                        "filename": fname,
                        "relative_path": os.path.relpath(fpath, self._codeium_root),
                    },
                ))

        return results
