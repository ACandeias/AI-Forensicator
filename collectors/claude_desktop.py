"""Collector for Claude Desktop app artifacts (~/Library/Application Support/Claude/)."""

import json
import os
import re
import sqlite3
from typing import Any, Dict, List, Optional

from collectors.base import AbstractCollector
from config import ARTIFACT_PATHS
from normalizer import sanitize_content

# Keys in LevelDB that may contain credentials -- filter from extraction
LEVELDB_SENSITIVE_KEYS = {
    "token", "auth", "cookie", "session", "password",
    "secret", "credential", "oauth",
}


def _filter_leveldb_strings(strings):
    """Remove LevelDB entries whose content contains sensitive key names."""
    filtered = []
    for entry in strings:
        content_lower = entry.get("content", "").lower()
        if any(key in content_lower for key in LEVELDB_SENSITIVE_KEYS):
            continue
        filtered.append(entry)
    return filtered


class ClaudeDesktopCollector(AbstractCollector):
    """Collect artifacts from the Claude Desktop Electron app.

    Artifact root: ~/Library/Application Support/Claude/
    Expected size: ~9.5 GB on active installations (dominated by Electron caches).
    """

    def __init__(self) -> None:
        super().__init__()
        self._root = ARTIFACT_PATHS["claude_desktop"]

    @property
    def name(self) -> str:
        return "Claude Desktop"

    def detect(self) -> bool:
        return os.path.isdir(self._root)

    def collect(self) -> List:
        artifacts = []  # type: List[Any]
        artifacts.extend(self._collect_config())
        artifacts.extend(self._collect_app_config())
        artifacts.extend(self._collect_session_storage())
        artifacts.extend(self._collect_local_storage())
        artifacts.extend(self._collect_indexed_db())
        artifacts.extend(self._collect_preferences())
        artifacts.extend(self._collect_sqlite_dbs())
        return artifacts

    # ------------------------------------------------------------------
    # 1. claude_desktop_config.json -- MCP server config
    # ------------------------------------------------------------------
    def _collect_config(self) -> List:
        """Parse claude_desktop_config.json for MCP server names and trusted
        folders.  SECURITY: flag env blocks but do NOT extract API keys.
        Artifact type: config."""
        results = []  # type: List[Any]
        path = os.path.join(self._root, "claude_desktop_config.json")
        if not os.path.isfile(path):
            return results

        data = self._safe_read_json(path)
        if data is None:
            return results

        fmeta = self._file_metadata(path)
        file_hash = self._hash_file(path)

        # Extract MCP server names without leaking env values
        mcp_servers = []  # type: List[str]
        env_risk_servers = []  # type: List[str]
        sanitized_data = {}  # type: Dict[str, Any]

        if isinstance(data, dict):
            servers_block = data.get("mcpServers", {})
            if isinstance(servers_block, dict):
                for server_name, server_cfg in servers_block.items():
                    mcp_servers.append(server_name)
                    # Flag servers with env blocks
                    if isinstance(server_cfg, dict) and "env" in server_cfg:
                        env_risk_servers.append(server_name)

                # Build sanitized copy: redact env values in each server
                sanitized_servers = {}
                for server_name, server_cfg in servers_block.items():
                    if isinstance(server_cfg, dict):
                        cleaned = dict(server_cfg)
                        if "env" in cleaned and isinstance(cleaned["env"], dict):
                            cleaned["env"] = {k: "[REDACTED]" for k in cleaned["env"]}
                        sanitized_servers[server_name] = cleaned
                    else:
                        sanitized_servers[server_name] = server_cfg
                sanitized_data["mcpServers"] = sanitized_servers

            # Copy non-MCP keys as-is (trusted folders, etc.)
            for k, v in data.items():
                if k != "mcpServers":
                    sanitized_data[k] = v

        trusted_folders = []  # type: List[str]
        if isinstance(data, dict):
            tf = data.get("trustedFolders", data.get("trusted_folders", []))
            if isinstance(tf, list):
                trusted_folders = [str(f) for f in tf]

        results.append(self._make_artifact(
            artifact_type="config",
            file_path=path,
            file_hash_sha256=file_hash,
            file_size_bytes=fmeta.get("file_size_bytes"),
            file_modified=fmeta.get("file_modified"),
            file_created=fmeta.get("file_created"),
            content_preview=self._content_preview(json.dumps(sanitized_data)),
            raw_data=json.dumps(sanitized_data),
            metadata={
                "mcp_server_names": mcp_servers,
                "mcp_server_count": len(mcp_servers),
                "env_risk_servers": env_risk_servers,
                "credential_risk": len(env_risk_servers) > 0,
                "trusted_folders": trusted_folders,
                "security_note": "env blocks in MCP servers may contain API keys; values redacted",
            },
        ))

        return results

    # ------------------------------------------------------------------
    # 2. config.json -- app config (filter out oauth:tokenCache)
    # ------------------------------------------------------------------
    def _collect_app_config(self) -> List:
        """Parse config.json, filtering out oauth:tokenCache.
        Artifact type: config."""
        results = []  # type: List[Any]
        path = os.path.join(self._root, "config.json")
        if not os.path.isfile(path):
            return results

        data = self._safe_read_json(path)
        if data is None:
            return results

        fmeta = self._file_metadata(path)
        file_hash = self._hash_file(path)

        # Filter out any oauth-related keys (tokens, caches, etc.)
        sanitized_data = {}  # type: Dict[str, Any]
        if isinstance(data, dict):
            for key, value in data.items():
                if "oauth" in key.lower():
                    sanitized_data[key] = "[FILTERED - oauth data]"
                else:
                    sanitized_data[key] = value
        else:
            sanitized_data = data

        results.append(self._make_artifact(
            artifact_type="config",
            file_path=path,
            file_hash_sha256=file_hash,
            file_size_bytes=fmeta.get("file_size_bytes"),
            file_modified=fmeta.get("file_modified"),
            file_created=fmeta.get("file_created"),
            content_preview=self._content_preview(json.dumps(sanitized_data)),
            raw_data=json.dumps(sanitized_data),
            metadata={
                "config_type": "app_config",
                "key_count": len(sanitized_data) if isinstance(sanitized_data, dict) else 0,
                "has_oauth_data": isinstance(data, dict) and any(
                    "oauth" in k.lower() for k in data.keys()
                ),
            },
        ))

        return results

    # ------------------------------------------------------------------
    # 3. Session Storage/ -- LevelDB string extraction
    # ------------------------------------------------------------------
    def _collect_session_storage(self) -> List:
        """Extract strings from Session Storage/ LevelDB.  Look for
        conversation UUIDs.  Artifact type: session_storage."""
        results = []  # type: List[Any]
        ss_dir = os.path.join(self._root, "Session Storage")
        if not os.path.isdir(ss_dir):
            return results

        strings = _filter_leveldb_strings(self._extract_leveldb_strings(ss_dir))
        uuid_pattern = re.compile(
            r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}',
            re.IGNORECASE,
        )

        conversation_ids = set()  # type: set
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
                "conversation_ids": sorted(conversation_ids)[:50],  # cap at 50
                "source_files": list(set(e.get("source_file", "") for e in strings)),
            },
        ))

        return results

    # ------------------------------------------------------------------
    # 4. Local Storage/leveldb/ -- LevelDB extraction
    # ------------------------------------------------------------------
    def _collect_local_storage(self) -> List:
        """Extract strings from Local Storage/leveldb/.  Look for
        tipTapEditorState drafts.  Artifact type: local_storage."""
        results = []  # type: List[Any]
        ls_dir = os.path.join(self._root, "Local Storage", "leveldb")
        if not os.path.isdir(ls_dir):
            return results

        strings = _filter_leveldb_strings(self._extract_leveldb_strings(ls_dir))

        # Look for tipTapEditorState entries (draft messages)
        drafts = []  # type: List[Dict[str, Any]]
        for entry in strings:
            content = entry.get("content", "")
            if "tipTapEditorState" in content or "tiptapEditorState" in content:
                json_data = entry.get("json_data")
                if json_data is not None:
                    drafts.append({
                        "source_file": entry.get("source_file", ""),
                        "preview": self._content_preview(content),
                    })
                else:
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
                "drafts": drafts[:20],  # cap at 20
                "source_files": list(set(e.get("source_file", "") for e in strings)),
            },
        ))

        return results

    # ------------------------------------------------------------------
    # 5. IndexedDB/https_claude.ai_0.indexeddb.leveldb/ -- IndexedDB
    # ------------------------------------------------------------------
    def _collect_indexed_db(self) -> List:
        """Extract strings from IndexedDB LevelDB for claude.ai.
        Artifact type: indexed_db."""
        results = []  # type: List[Any]
        idb_dir = os.path.join(
            self._root, "IndexedDB",
            "https_claude.ai_0.indexeddb.leveldb",
        )
        if not os.path.isdir(idb_dir):
            return results

        strings = _filter_leveldb_strings(self._extract_leveldb_strings(idb_dir))

        # Categorize extracted strings
        json_entries = [e for e in strings if "json_data" in e]
        uuid_pattern = re.compile(
            r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}',
            re.IGNORECASE,
        )
        conversation_ids = set()  # type: set
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

    # ------------------------------------------------------------------
    # 6. Preferences -- JSON preferences
    # ------------------------------------------------------------------
    def _collect_preferences(self) -> List:
        """Parse the Preferences JSON file.
        Artifact type: preferences."""
        results = []  # type: List[Any]
        path = os.path.join(self._root, "Preferences")
        if not os.path.isfile(path):
            return results

        data = self._safe_read_json(path)
        if data is None:
            return results

        fmeta = self._file_metadata(path)
        file_hash = self._hash_file(path)

        # Sanitize any credential-like content
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

    # ------------------------------------------------------------------
    # 7. Conversions DB -- SQLite (135KB)
    # ------------------------------------------------------------------
    def _collect_sqlite_dbs(self) -> List:
        """Read the Conversions SQLite DB with immutable flag.
        Artifact type: sqlite_data."""
        results = []  # type: List[Any]

        # The Conversions DB
        db_path = os.path.join(self._root, "Conversions")
        if not os.path.isfile(db_path):
            return results

        fmeta = self._file_metadata(db_path)
        file_hash = self._hash_file(db_path)

        # List all tables in the database
        tables = self._safe_sqlite_read(
            db_path,
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name",
        )
        table_names = [t.get("name", "") for t in tables]

        # Get row counts for each table
        table_info = {}  # type: Dict[str, int]
        for tname in table_names:
            # Validate table name to prevent injection (alphanumeric and underscore only)
            if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', tname):
                continue
            rows = self._safe_sqlite_read(
                db_path,
                "SELECT COUNT(*) as cnt FROM \"{}\"".format(tname),
            )
            if rows:
                table_info[tname] = rows[0].get("cnt", 0)

        results.append(self._make_artifact(
            artifact_type="sqlite_data",
            file_path=db_path,
            file_hash_sha256=file_hash,
            file_size_bytes=fmeta.get("file_size_bytes"),
            file_modified=fmeta.get("file_modified"),
            file_created=fmeta.get("file_created"),
            content_preview="Conversions DB: {} tables, {} total rows".format(
                len(table_names),
                sum(table_info.values()),
            ),
            metadata={
                "database_name": "Conversions",
                "tables": table_names,
                "table_row_counts": table_info,
            },
        ))

        return results
