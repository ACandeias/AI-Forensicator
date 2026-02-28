"""Reusable mixin classes for AIFT collectors.

These mixins extract common patterns from existing collectors to avoid
code duplication across 30+ new collector implementations.
"""

import json
import os
import plistlib
import re
from typing import Any, Dict, List, Optional

from config import AI_URL_PATTERNS, ARTIFACT_PATHS
from normalizer import sanitize_content


# Keys in LevelDB that may contain credentials -- filter from extraction
LEVELDB_SENSITIVE_KEYS = {
    "token", "auth", "cookie", "session", "password",
    "secret", "credential", "oauth",
}


def _build_url_or_clause(column, patterns):
    """Build a SQL OR clause matching a column against URL patterns."""
    clauses = ["{} LIKE ?".format(column) for _ in patterns]
    return "(" + " OR ".join(clauses) + ")"


def _filter_leveldb_strings(strings):
    """Remove LevelDB entries whose content contains sensitive key names."""
    filtered = []
    for entry in strings:
        content_lower = entry.get("content", "").lower()
        if any(key in content_lower for key in LEVELDB_SENSITIVE_KEYS):
            continue
        filtered.append(entry)
    return filtered


class ChromiumHistoryMixin:
    """Mixin for Chromium-based browser history collection.

    Subclasses must provide:
    - self._history_db_path() -> Optional[str]  -- path to the History SQLite DB
    - Inherits from AbstractCollector (provides _safe_sqlite_read,
      _parse_chrome_timestamp, _content_preview, _make_artifact)
    """

    def _collect_chromium_history(self, db_path):
        """Query a Chromium History DB for AI-related URL visits.

        Returns List[AIArtifact].
        """
        if not db_path or not os.path.isfile(db_path):
            return []

        url_filter = _build_url_or_clause("u.url", AI_URL_PATTERNS)
        query = (
            "SELECT u.url, u.title, v.visit_time, v.visit_duration "
            "FROM urls u JOIN visits v ON u.id = v.url "
            "WHERE " + url_filter + " "
            "ORDER BY v.visit_time DESC"
        )

        rows = self._safe_sqlite_read(db_path, query, tuple(AI_URL_PATTERNS))
        artifacts = []

        for row in rows:
            url = row.get("url", "")
            title = row.get("title", "")
            visit_time = row.get("visit_time")
            visit_duration = row.get("visit_duration", 0)

            ts = self._parse_chrome_timestamp(visit_time)
            preview = self._content_preview("{} - {}".format(title, url))

            metadata = {
                "url": url,
                "title": title,
                "visit_duration_us": visit_duration,
            }

            artifacts.append(self._make_artifact(
                artifact_type="browser_history",
                timestamp=ts,
                file_path=db_path,
                content_preview=preview,
                metadata=metadata,
            ))

        return artifacts

    def _find_chromium_history_db(self, base_path, profile_subdir=None):
        """Locate a Chromium History file under a base path.

        If profile_subdir is given (e.g. "Default"), checks that path directly.
        Otherwise searches for User Data/*/History or Default/History.
        Returns the path string or None.
        """
        if profile_subdir:
            path = os.path.join(base_path, profile_subdir, "History")
            if os.path.isfile(path):
                return path
            return None

        # Check Default directly
        default_path = os.path.join(base_path, "Default", "History")
        if os.path.isfile(default_path):
            return default_path

        # Check User Data/<profile>/History
        user_data = os.path.join(base_path, "User Data")
        if os.path.isdir(user_data):
            try:
                for entry in os.listdir(user_data):
                    profile_dir = os.path.join(user_data, entry)
                    if not os.path.isdir(profile_dir):
                        continue
                    history_file = os.path.join(profile_dir, "History")
                    if os.path.isfile(history_file):
                        return history_file
            except OSError:
                pass

        return None


class OpenAIDataMixin:
    """Mixin for OpenAI app artifacts (.data files, plists).

    Subclasses must provide:
    - Inherits from AbstractCollector (provides _file_metadata, _hash_file,
      _content_preview, _make_artifact)
    """

    def _collect_encrypted_data_files(self, root_dir, tool_name="OpenAI"):
        """Walk a directory for .data files (CK-encrypted binary).

        Collects metadata only -- no content extraction.
        Returns List[AIArtifact].
        """
        results = []
        data_files = []
        total_size = 0

        for dirpath, _dirnames, filenames in os.walk(root_dir):
            # Skip symlinks
            if os.path.islink(dirpath):
                continue
            for fname in filenames:
                if not fname.endswith(".data"):
                    continue
                fpath = os.path.join(dirpath, fname)
                if not os.path.isfile(fpath) or os.path.islink(fpath):
                    continue

                fmeta = self._file_metadata(fpath)
                size = fmeta.get("file_size_bytes") or 0
                total_size += size

                data_files.append({
                    "filename": fname,
                    "path": fpath,
                    "size_bytes": size,
                    "modified": fmeta.get("file_modified"),
                    "created": fmeta.get("file_created"),
                })

        if not data_files:
            return results

        data_files.sort(
            key=lambda x: x.get("modified") or "",
            reverse=True,
        )

        results.append(self._make_artifact(
            artifact_type="encrypted_conversation",
            file_path=root_dir,
            content_preview="{}: {} encrypted .data files, {:.1f} MB total".format(
                tool_name, len(data_files),
                total_size / (1024 * 1024),
            ),
            metadata={
                "file_count": len(data_files),
                "total_size_bytes": total_size,
                "total_size_mb": round(total_size / (1024 * 1024), 2),
                "encryption_type": "CloudKit (CK-encrypted)",
                "content_accessible": False,
                "newest_file": data_files[0] if data_files else None,
                "oldest_file": data_files[-1] if data_files else None,
                "security_note": "Files are CK-encrypted; content not extracted",
            },
        ))

        for df in data_files:
            file_hash = self._hash_file(df["path"])
            results.append(self._make_artifact(
                artifact_type="encrypted_conversation",
                file_path=df["path"],
                file_hash_sha256=file_hash,
                file_size_bytes=df.get("size_bytes"),
                file_modified=df.get("modified"),
                file_created=df.get("created"),
                content_preview="Encrypted .data file: {} ({} bytes)".format(
                    df["filename"], df.get("size_bytes", 0),
                ),
                metadata={
                    "filename": df["filename"],
                    "encryption_type": "CloudKit (CK-encrypted)",
                    "content_accessible": False,
                },
            ))

        return results

    def _safe_read_plist(self, path):
        """Safely read a plist file (binary or XML format)."""
        try:
            with open(path, "rb") as f:
                return plistlib.load(f)
        except (plistlib.InvalidFileException, OSError, IOError, Exception):
            return None

    def _plist_to_json_safe(self, obj):
        """Convert plist data types to JSON-serializable types."""
        if isinstance(obj, dict):
            return {str(k): self._plist_to_json_safe(v) for k, v in obj.items()}
        if isinstance(obj, (list, tuple)):
            return [self._plist_to_json_safe(item) for item in obj]
        if isinstance(obj, bytes):
            if len(obj) <= 64:
                return "<binary:{}>".format(obj.hex())
            return "<binary:{}... ({} bytes)>".format(obj[:32].hex(), len(obj))
        if isinstance(obj, (int, float, str, bool)):
            return obj
        return str(obj)

    def _collect_plist_preferences(self, path, tool_name="OpenAI"):
        """Parse a plist file and return preference artifacts.

        Returns List[AIArtifact].
        """
        results = []
        if not os.path.isfile(path):
            return results

        fmeta = self._file_metadata(path)
        file_hash = self._hash_file(path)

        plist_data = self._safe_read_plist(path)
        if plist_data is None:
            return results

        safe_data = self._plist_to_json_safe(plist_data)
        sanitized_text = sanitize_content(json.dumps(safe_data, default=str))

        results.append(self._make_artifact(
            artifact_type="preferences",
            file_path=path,
            file_hash_sha256=file_hash,
            file_size_bytes=fmeta.get("file_size_bytes"),
            file_modified=fmeta.get("file_modified"),
            file_created=fmeta.get("file_created"),
            content_preview=self._content_preview(sanitized_text),
            raw_data=sanitized_text,
            metadata={
                "plist_key_count": len(safe_data) if isinstance(safe_data, dict) else 0,
                "plist_keys": list(safe_data.keys()) if isinstance(safe_data, dict) else [],
            },
        ))

        return results


class ElectronAppMixin:
    """Mixin for Electron app artifacts (LevelDB, IndexedDB, Session Storage).

    Subclasses must provide:
    - Inherits from AbstractCollector (provides _extract_leveldb_strings,
      _file_metadata, _content_preview, _make_artifact)
    """

    def _collect_electron_session_storage(self, app_root, indexeddb_origin=None):
        """Extract strings from Session Storage LevelDB.

        Returns List[AIArtifact].
        """
        results = []
        ss_dir = os.path.join(app_root, "Session Storage")
        if not os.path.isdir(ss_dir):
            return results

        strings = _filter_leveldb_strings(self._extract_leveldb_strings(ss_dir))
        uuid_pattern = re.compile(
            r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}',
            re.IGNORECASE,
        )

        conversation_ids = set()
        for entry in strings:
            content = entry.get("content", "")
            for match in uuid_pattern.finditer(content):
                conversation_ids.add(match.group(0))

        fmeta = self._file_metadata(ss_dir)

        results.append(self._make_artifact(
            artifact_type="session_storage",
            file_path=ss_dir,
            file_size_bytes=fmeta.get("file_size_bytes"),
            file_modified=fmeta.get("file_modified"),
            file_created=fmeta.get("file_created"),
            content_preview="Session Storage LevelDB: {} strings extracted, {} conversation UUIDs".format(
                len(strings), len(conversation_ids),
            ),
            metadata={
                "strings_extracted": len(strings),
                "conversation_uuids_found": len(conversation_ids),
                "conversation_ids": sorted(conversation_ids)[:50],
                "source_files": list(set(e.get("source_file", "") for e in strings)),
            },
        ))

        return results

    def _collect_electron_local_storage(self, app_root):
        """Extract strings from Local Storage LevelDB.

        Returns List[AIArtifact].
        """
        results = []
        ls_dir = os.path.join(app_root, "Local Storage", "leveldb")
        if not os.path.isdir(ls_dir):
            return results

        strings = _filter_leveldb_strings(self._extract_leveldb_strings(ls_dir))

        drafts = []
        for entry in strings:
            content = entry.get("content", "")
            if "tipTapEditorState" in content or "tiptapEditorState" in content:
                drafts.append({
                    "source_file": entry.get("source_file", ""),
                    "preview": self._content_preview(content),
                })

        fmeta = self._file_metadata(ls_dir)

        results.append(self._make_artifact(
            artifact_type="local_storage",
            file_path=ls_dir,
            file_size_bytes=fmeta.get("file_size_bytes"),
            file_modified=fmeta.get("file_modified"),
            file_created=fmeta.get("file_created"),
            content_preview="Local Storage LevelDB: {} strings extracted, {} draft entries".format(
                len(strings), len(drafts),
            ),
            metadata={
                "strings_extracted": len(strings),
                "draft_entries_found": len(drafts),
                "drafts": drafts[:20],
                "source_files": list(set(e.get("source_file", "") for e in strings)),
            },
        ))

        return results

    def _collect_electron_indexed_db(self, app_root, origin_pattern=None):
        """Extract strings from IndexedDB LevelDB directories.

        If origin_pattern is provided (e.g. "https_claude.ai_0"), only that
        subdirectory is checked.  Otherwise walks all IndexedDB subdirs.

        Returns List[AIArtifact].
        """
        results = []
        idb_base = os.path.join(app_root, "IndexedDB")
        if not os.path.isdir(idb_base):
            return results

        # Find IndexedDB directories to scan
        idb_dirs = []
        if origin_pattern:
            candidate = os.path.join(idb_base, origin_pattern + ".indexeddb.leveldb")
            if os.path.isdir(candidate):
                idb_dirs.append(candidate)
        else:
            try:
                for entry in os.listdir(idb_base):
                    candidate = os.path.join(idb_base, entry)
                    if os.path.isdir(candidate) and entry.endswith(".indexeddb.leveldb"):
                        idb_dirs.append(candidate)
            except OSError:
                pass

        for idb_dir in idb_dirs:
            strings = _filter_leveldb_strings(self._extract_leveldb_strings(idb_dir))

            json_entries = [e for e in strings if "json_data" in e]
            uuid_pattern = re.compile(
                r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}',
                re.IGNORECASE,
            )
            conversation_ids = set()
            for entry in strings:
                for match in uuid_pattern.finditer(entry.get("content", "")):
                    conversation_ids.add(match.group(0))

            fmeta = self._file_metadata(idb_dir)

            results.append(self._make_artifact(
                artifact_type="indexed_db",
                file_path=idb_dir,
                file_size_bytes=fmeta.get("file_size_bytes"),
                file_modified=fmeta.get("file_modified"),
                file_created=fmeta.get("file_created"),
                content_preview="IndexedDB: {} strings, {} JSON entries, {} UUIDs".format(
                    len(strings), len(json_entries), len(conversation_ids),
                ),
                metadata={
                    "strings_extracted": len(strings),
                    "json_entries": len(json_entries),
                    "conversation_uuids_found": len(conversation_ids),
                    "conversation_ids": sorted(conversation_ids)[:50],
                    "source_files": list(set(e.get("source_file", "") for e in strings)),
                },
            ))

        return results

    def _collect_electron_preferences(self, app_root):
        """Parse the Preferences JSON file.

        Returns List[AIArtifact].
        """
        results = []
        path = os.path.join(app_root, "Preferences")
        if not os.path.isfile(path):
            return results

        data = self._safe_read_json(path)
        if data is None:
            return results

        fmeta = self._file_metadata(path)
        file_hash = self._hash_file(path)

        sanitized_text = sanitize_content(json.dumps(data))

        results.append(self._make_artifact(
            artifact_type="preferences",
            file_path=path,
            file_hash_sha256=file_hash,
            file_size_bytes=fmeta.get("file_size_bytes"),
            file_modified=fmeta.get("file_modified"),
            file_created=fmeta.get("file_created"),
            content_preview=self._content_preview(sanitized_text),
            raw_data=sanitized_text,
            metadata={
                "key_count": len(data) if isinstance(data, dict) else 0,
            },
        ))

        return results


class VSCodeExtensionMixin:
    """Mixin for VS Code extension globalStorage artifacts.

    Extension data lives under:
    ~/Library/Application Support/Code/User/globalStorage/<extension-id>/

    Subclasses must provide:
    - Inherits from AbstractCollector (provides _safe_read_json, _safe_read_text,
      _file_metadata, _hash_file, _content_preview, _make_artifact)
    """

    def _get_extension_storage_path(self, extension_id):
        """Return the globalStorage path for a given extension ID."""
        return os.path.join(
            ARTIFACT_PATHS.get("vscode", ""),
            "User", "globalStorage", extension_id,
        )

    def _collect_extension_json_files(self, storage_path, artifact_type="extension_data"):
        """Walk an extension's globalStorage directory and collect JSON files.

        Returns List[AIArtifact].
        """
        results = []
        if not os.path.isdir(storage_path):
            return results

        for dirpath, _dirnames, filenames in os.walk(storage_path):
            if os.path.islink(dirpath):
                continue
            for fname in filenames:
                if not (fname.endswith(".json") or fname.endswith(".yaml") or fname.endswith(".yml")):
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

                # Sanitize content
                sanitized = sanitize_content(preview_text)

                rel_path = os.path.relpath(fpath, storage_path)

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

    def _collect_extension_state_vscdb(self, storage_path, table_name="ItemTable"):
        """Query a state.vscdb SQLite database in the extension's storage.

        Returns List[AIArtifact].
        """
        results = []
        db_path = os.path.join(storage_path, "state.vscdb")
        if not os.path.isfile(db_path):
            return results

        fmeta = self._file_metadata(db_path)
        file_hash = self._hash_file(db_path)

        # Validate table name
        if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', table_name):
            return results

        rows = self._safe_sqlite_read(
            db_path,
            "SELECT key, value FROM \"{}\"".format(table_name),
        )

        for row in rows:
            key = row.get("key", "")
            raw_value = row.get("value", "")

            # Skip credential-like keys
            if any(s in key.lower() for s in LEVELDB_SENSITIVE_KEYS):
                continue

            sanitized = sanitize_content(str(raw_value)[:10000]) if raw_value else ""

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


class LocalLLMRunnerMixin:
    """Mixin for local LLM runner model inventory collection.

    Walks model directories and collects file metadata (names, sizes, digests)
    WITHOUT reading binary model blob content.

    Subclasses must provide:
    - Inherits from AbstractCollector (provides _file_metadata, _hash_file,
      _safe_read_json, _content_preview, _make_artifact)
    """

    def _collect_model_inventory(self, models_dir, tool_name="LLM Runner"):
        """Walk a model directory and collect metadata about model files.

        Returns List[AIArtifact].
        """
        results = []
        if not os.path.isdir(models_dir):
            return results

        model_entries = []
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

                rel_path = os.path.relpath(fpath, models_dir)

                # Collect manifest/config files content, skip binary blobs
                is_metadata_file = fname.endswith((".json", ".yaml", ".yml", ".txt"))

                entry = {
                    "filename": fname,
                    "relative_path": rel_path,
                    "size_bytes": size,
                    "modified": fmeta.get("file_modified"),
                    "is_metadata": is_metadata_file,
                }

                model_entries.append(entry)

        if not model_entries:
            return results

        # Summary artifact
        metadata_files = [e for e in model_entries if e.get("is_metadata")]
        binary_files = [e for e in model_entries if not e.get("is_metadata")]

        results.append(self._make_artifact(
            artifact_type="model_inventory",
            file_path=models_dir,
            content_preview="{}: {} model files, {:.1f} GB total".format(
                tool_name, len(model_entries),
                total_size / (1024 * 1024 * 1024),
            ),
            metadata={
                "total_files": len(model_entries),
                "metadata_files": len(metadata_files),
                "binary_files": len(binary_files),
                "total_size_bytes": total_size,
                "total_size_gb": round(total_size / (1024 * 1024 * 1024), 2),
            },
        ))

        # Collect individual manifest/config files
        for entry in metadata_files:
            fpath = os.path.join(models_dir, entry["relative_path"])
            data = self._safe_read_json(fpath)
            if data is not None:
                sanitized = sanitize_content(json.dumps(data))
                results.append(self._make_artifact(
                    artifact_type="model_config",
                    file_path=fpath,
                    file_hash_sha256=self._hash_file(fpath),
                    file_size_bytes=entry.get("size_bytes"),
                    file_modified=entry.get("modified"),
                    content_preview=self._content_preview(sanitized),
                    raw_data=sanitized if len(sanitized) < 50000 else None,
                    metadata={
                        "filename": entry["filename"],
                        "relative_path": entry["relative_path"],
                    },
                ))

        return results

    def _collect_model_manifests(self, manifests_dir, tool_name="LLM Runner"):
        """Collect model manifest files (e.g. Ollama manifests).

        Reads JSON manifests to extract model names, digests, and sizes
        without reading blob content.

        Returns List[AIArtifact].
        """
        results = []
        if not os.path.isdir(manifests_dir):
            return results

        model_info = []

        for dirpath, _dirnames, filenames in os.walk(manifests_dir):
            if os.path.islink(dirpath):
                continue
            for fname in filenames:
                fpath = os.path.join(dirpath, fname)
                if os.path.islink(fpath) or not os.path.isfile(fpath):
                    continue

                data = self._safe_read_json(fpath)
                if data is None:
                    continue

                fmeta = self._file_metadata(fpath)
                rel_path = os.path.relpath(fpath, manifests_dir)

                # Extract model info from manifest
                layers = data.get("layers", [])
                total_layer_size = sum(
                    l.get("size", 0) for l in layers if isinstance(l, dict)
                )

                model_info.append({
                    "model_path": rel_path,
                    "layer_count": len(layers),
                    "total_size_bytes": total_layer_size,
                    "config_digest": data.get("config", {}).get("digest", "") if isinstance(data.get("config"), dict) else "",
                })

                sanitized = sanitize_content(json.dumps(data))

                results.append(self._make_artifact(
                    artifact_type="model_manifest",
                    file_path=fpath,
                    file_hash_sha256=self._hash_file(fpath),
                    file_size_bytes=fmeta.get("file_size_bytes"),
                    file_modified=fmeta.get("file_modified"),
                    file_created=fmeta.get("file_created"),
                    content_preview=self._content_preview(
                        "{}: model {} ({} layers)".format(
                            tool_name, rel_path, len(layers),
                        )
                    ),
                    raw_data=sanitized if len(sanitized) < 50000 else None,
                    metadata={
                        "model_path": rel_path,
                        "layer_count": len(layers),
                        "total_layer_size_bytes": total_layer_size,
                    },
                ))

        if model_info:
            results.insert(0, self._make_artifact(
                artifact_type="model_inventory",
                file_path=manifests_dir,
                content_preview="{}: {} models in manifest directory".format(
                    tool_name, len(model_info),
                ),
                metadata={
                    "model_count": len(model_info),
                    "models": model_info,
                },
            ))

        return results
