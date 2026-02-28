"""Collector for Cursor IDE artifacts (~/Library/Application Support/Cursor/)."""

import json
import os
import re
from typing import Any, Dict, List, Optional

from collectors.base import AbstractCollector
from config import ARTIFACT_PATHS
from normalizer import sanitize_content, estimate_model_from_content


class CursorCollector(AbstractCollector):
    """Collect artifacts from the Cursor IDE application.

    Artifact root: ~/Library/Application Support/Cursor/
    Primary data source: User/globalStorage/state.vscdb (SQLite)
    Key tables: cursorDiskKV, ItemTable
    """

    def __init__(self) -> None:
        super().__init__()
        self._root = ARTIFACT_PATHS["cursor"]

    @property
    def name(self) -> str:
        return "Cursor"

    def detect(self) -> bool:
        return os.path.isdir(self._root)

    def collect(self) -> List:
        artifacts = []  # type: List[Any]
        artifacts.extend(self._collect_composer_sessions())
        artifacts.extend(self._collect_bubble_messages())
        artifacts.extend(self._collect_usage_stats())
        artifacts.extend(self._collect_auth_flags())
        return artifacts

    def _get_state_db_path(self) -> Optional[str]:
        """Locate state.vscdb in the User/globalStorage directory."""
        path = os.path.join(self._root, "User", "globalStorage", "state.vscdb")
        if os.path.isfile(path):
            return path
        return None

    # ------------------------------------------------------------------
    # 1. composerData:* -- AI chat sessions from cursorDiskKV
    # ------------------------------------------------------------------
    def _collect_composer_sessions(self) -> List:
        """Query cursorDiskKV table for composerData:* keys containing
        AI chat sessions.  Artifact type: conversation."""
        results = []  # type: List[Any]
        db_path = self._get_state_db_path()
        if db_path is None:
            return results

        fmeta = self._file_metadata(db_path)
        file_hash = self._hash_file(db_path)

        rows = self._safe_sqlite_read(
            db_path,
            "SELECT key, value FROM cursorDiskKV WHERE key LIKE 'composerData:%'",
        )

        for row in rows:
            key = row.get("key", "")
            raw_value = row.get("value", "")

            # composerData keys are typically composerData:<uuid>
            composer_id = key.replace("composerData:", "", 1) if key.startswith("composerData:") else key

            # Try to parse the value as JSON
            parsed = None  # type: Optional[Dict[str, Any]]
            try:
                if raw_value:
                    parsed = json.loads(raw_value)
            except (json.JSONDecodeError, ValueError, TypeError):
                pass

            # Extract useful fields from the composer data
            preview_text = ""
            model = None  # type: Optional[str]
            message_count = 0

            if isinstance(parsed, dict):
                # Look for conversation content
                messages = parsed.get("conversation", parsed.get("messages", []))
                if isinstance(messages, list):
                    message_count = len(messages)
                    # Build a preview from the first message
                    for msg in messages[:3]:
                        if isinstance(msg, dict):
                            text = msg.get("text", msg.get("content", ""))
                            if text:
                                preview_text += str(text) + " "

                # Try to identify the model
                model = parsed.get("model", parsed.get("modelId"))
                if not model and preview_text:
                    model = estimate_model_from_content(preview_text)

                # Check for title/name
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
    # 2. bubbleId:* -- individual messages from cursorDiskKV
    # ------------------------------------------------------------------
    def _collect_bubble_messages(self) -> List:
        """Query cursorDiskKV table for bubbleId:* keys containing
        individual chat messages.  Artifact type: conversation_message."""
        results = []  # type: List[Any]
        db_path = self._get_state_db_path()
        if db_path is None:
            return results

        fmeta = self._file_metadata(db_path)
        file_hash = self._hash_file(db_path)

        rows = self._safe_sqlite_read(
            db_path,
            "SELECT key, value FROM cursorDiskKV WHERE key LIKE 'bubbleId:%'",
        )

        for row in rows:
            key = row.get("key", "")
            raw_value = row.get("value", "")

            bubble_id = key.replace("bubbleId:", "", 1) if key.startswith("bubbleId:") else key

            # Try to parse as JSON
            parsed = None  # type: Optional[Dict[str, Any]]
            try:
                if raw_value:
                    parsed = json.loads(raw_value)
            except (json.JSONDecodeError, ValueError, TypeError):
                pass

            content_text = ""
            role = None  # type: Optional[str]
            model = None  # type: Optional[str]
            conversation_id = None  # type: Optional[str]

            if isinstance(parsed, dict):
                content_text = str(
                    parsed.get("text",
                    parsed.get("content",
                    parsed.get("message", "")))
                )
                role = parsed.get("role", parsed.get("type"))
                model = parsed.get("model", parsed.get("modelId"))
                conversation_id = parsed.get("composerId", parsed.get("conversationId"))
                if not model and content_text:
                    model = estimate_model_from_content(content_text)
            elif raw_value:
                content_text = str(raw_value)

            results.append(self._make_artifact(
                artifact_type="conversation_message",
                file_path=db_path,
                file_hash_sha256=file_hash,
                file_size_bytes=fmeta.get("file_size_bytes"),
                file_modified=fmeta.get("file_modified"),
                file_created=fmeta.get("file_created"),
                content_preview=self._content_preview(content_text),
                message_role=role,
                model_identified=model,
                conversation_id=conversation_id,
                token_estimate=self._estimate_tokens(content_text),
                metadata={
                    "db_key": key,
                    "bubble_id": bubble_id,
                    "value_size_bytes": len(raw_value) if raw_value else 0,
                },
            ))

        return results

    # ------------------------------------------------------------------
    # 3. ItemTable: aiCodeTracking.dailyStats.* -- usage statistics
    # ------------------------------------------------------------------
    def _collect_usage_stats(self) -> List:
        """Query ItemTable for aiCodeTracking.dailyStats.* keys.
        Artifact type: analytics."""
        results = []  # type: List[Any]
        db_path = self._get_state_db_path()
        if db_path is None:
            return results

        fmeta = self._file_metadata(db_path)
        file_hash = self._hash_file(db_path)

        rows = self._safe_sqlite_read(
            db_path,
            "SELECT key, value FROM ItemTable WHERE key LIKE 'aiCodeTracking.dailyStats.%'",
        )

        daily_stats = {}  # type: Dict[str, Any]
        for row in rows:
            key = row.get("key", "")
            raw_value = row.get("value", "")

            # Extract the date portion from the key
            date_part = key.replace("aiCodeTracking.dailyStats.", "", 1)

            parsed = None
            try:
                if raw_value:
                    parsed = json.loads(raw_value)
            except (json.JSONDecodeError, ValueError, TypeError):
                parsed = raw_value

            daily_stats[date_part] = parsed

        if not daily_stats:
            return results

        # Create a summary artifact for all daily stats
        results.append(self._make_artifact(
            artifact_type="analytics",
            file_path=db_path,
            file_hash_sha256=file_hash,
            file_size_bytes=fmeta.get("file_size_bytes"),
            file_modified=fmeta.get("file_modified"),
            file_created=fmeta.get("file_created"),
            content_preview="Cursor daily stats: {} days tracked".format(
                len(daily_stats),
            ),
            raw_data=json.dumps(daily_stats, default=str),
            metadata={
                "days_tracked": len(daily_stats),
                "date_range": {
                    "earliest": min(daily_stats.keys()) if daily_stats else None,
                    "latest": max(daily_stats.keys()) if daily_stats else None,
                },
                "daily_stats": daily_stats,
            },
        ))

        return results

    # ------------------------------------------------------------------
    # 4. SECURITY: flag cursorAuth tokens (never extract values)
    # ------------------------------------------------------------------
    def _collect_auth_flags(self) -> List:
        """Check for cursorAuth/accessToken and cursorAuth/refreshToken
        in cursorDiskKV.  SECURITY: flag their presence but NEVER extract
        the token values.  Artifact type: security_flag."""
        results = []  # type: List[Any]
        db_path = self._get_state_db_path()
        if db_path is None:
            return results

        fmeta = self._file_metadata(db_path)

        # Check for auth token keys -- only query for existence, not values
        auth_keys_to_check = [
            "cursorAuth/accessToken",
            "cursorAuth/refreshToken",
        ]

        found_keys = []  # type: List[str]
        for auth_key in auth_keys_to_check:
            # Query only the key column, never SELECT value for auth keys
            rows = self._safe_sqlite_read(
                db_path,
                "SELECT key FROM cursorDiskKV WHERE key = ?",
                (auth_key,),
            )
            if rows:
                found_keys.append(auth_key)

        if not found_keys:
            return results

        results.append(self._make_artifact(
            artifact_type="security_flag",
            file_path=db_path,
            file_size_bytes=fmeta.get("file_size_bytes"),
            file_modified=fmeta.get("file_modified"),
            file_created=fmeta.get("file_created"),
            content_preview="SECURITY: Auth tokens detected in Cursor state DB (values NOT extracted)",
            metadata={
                "credential_risk": True,
                "auth_keys_present": found_keys,
                "values_extracted": False,
                "security_note": "cursorAuth tokens found in state.vscdb; "
                                 "values intentionally NOT collected to prevent credential exposure",
            },
        ))

        return results
