"""Collector for Claude Code CLI artifacts (~/.claude/)."""

import json
import os
from typing import Any, Dict, List, Optional

from collectors.base import AbstractCollector
from config import ARTIFACT_PATHS
from normalizer import sanitize_content, estimate_model_from_content


class ClaudeCodeCollector(AbstractCollector):
    """Collect artifacts from the Claude Code CLI data directory.

    Artifact root: ~/.claude/
    Expected size: ~571 MB on active installations.
    """

    def __init__(self) -> None:
        super().__init__()
        self._root = ARTIFACT_PATHS["claude_code"]

    @property
    def name(self) -> str:
        return "Claude Code"

    def detect(self) -> bool:
        return os.path.isdir(self._root)

    def collect(self) -> List:
        artifacts = []  # type: List[Any]
        artifacts.extend(self._collect_history())
        artifacts.extend(self._collect_sessions())
        artifacts.extend(self._collect_settings())
        artifacts.extend(self._collect_stats())
        artifacts.extend(self._collect_plans())
        artifacts.extend(self._collect_tasks_teams())
        artifacts.extend(self._collect_debug_logs())
        return artifacts

    # ------------------------------------------------------------------
    # 1. history.jsonl -- prompt history
    # ------------------------------------------------------------------
    def _collect_history(self) -> List:
        """Parse history.jsonl: each line has display, timestamp (epoch ms),
        sessionId, and project.  Artifact type: prompt_history."""
        results = []  # type: List[Any]
        path = os.path.join(self._root, "history.jsonl")
        if not os.path.isfile(path):
            return results

        fmeta = self._file_metadata(path)
        file_hash = self._hash_file(path)

        for entry in self._safe_read_jsonl(path):
            display = entry.get("display", "")
            ts = self._parse_timestamp_ms(entry.get("timestamp"))
            session_id = entry.get("sessionId")
            project = entry.get("project")

            results.append(self._make_artifact(
                artifact_type="prompt_history",
                timestamp=ts,
                file_path=path,
                file_hash_sha256=file_hash,
                file_size_bytes=fmeta.get("file_size_bytes"),
                file_modified=fmeta.get("file_modified"),
                file_created=fmeta.get("file_created"),
                content_preview=self._content_preview(display),
                conversation_id=session_id,
                token_estimate=self._estimate_tokens(display),
                metadata={
                    "session_id": session_id,
                    "project": project,
                    "display": display,
                },
            ))

        return results

    # ------------------------------------------------------------------
    # 2. projects/*/*.jsonl -- session conversations
    # ------------------------------------------------------------------
    def _collect_sessions(self) -> List:
        """Walk projects/*/*.jsonl files (can be 5 MB+). Filter for
        user/assistant/system message types.  Artifact type: conversation_message."""
        results = []  # type: List[Any]
        projects_dir = os.path.join(self._root, "projects")
        if not os.path.isdir(projects_dir):
            return results

        for dirpath, _dirnames, filenames in os.walk(projects_dir):
            for fname in filenames:
                if not fname.endswith(".jsonl"):
                    continue
                fpath = os.path.join(dirpath, fname)
                results.extend(self._parse_session_file(fpath))

        return results

    def _parse_session_file(self, fpath: str) -> List:
        """Process a single session JSONL file line-by-line."""
        results = []  # type: List[Any]
        fmeta = self._file_metadata(fpath)
        file_hash = self._hash_file(fpath)

        # Derive a session id from the filename (strip .jsonl)
        session_id = os.path.splitext(os.path.basename(fpath))[0]

        for entry in self._safe_read_jsonl(fpath):
            msg_type = entry.get("type", "")
            if msg_type not in ("user", "assistant", "system"):
                continue

            message = entry.get("message", {})
            if not isinstance(message, dict):
                continue

            # Content can be a string or a list of content blocks
            raw_content = message.get("content", "")
            if isinstance(raw_content, list):
                # Concatenate text blocks
                text_parts = []
                for block in raw_content:
                    if isinstance(block, dict):
                        text_parts.append(block.get("text", ""))
                    elif isinstance(block, str):
                        text_parts.append(block)
                content_text = "\n".join(text_parts)
            else:
                content_text = str(raw_content)

            model = message.get("model") or estimate_model_from_content(content_text)
            ts = self._parse_timestamp_ms(entry.get("timestamp"))

            results.append(self._make_artifact(
                artifact_type="conversation_message",
                timestamp=ts,
                file_path=fpath,
                file_hash_sha256=file_hash,
                file_size_bytes=fmeta.get("file_size_bytes"),
                file_modified=fmeta.get("file_modified"),
                file_created=fmeta.get("file_created"),
                content_preview=self._content_preview(content_text),
                message_role=msg_type,
                model_identified=model,
                conversation_id=session_id,
                token_estimate=self._estimate_tokens(content_text),
                metadata={
                    "session_id": session_id,
                    "message_type": msg_type,
                },
            ))

        return results

    # ------------------------------------------------------------------
    # 3. settings.json -- configuration
    # ------------------------------------------------------------------
    def _collect_settings(self) -> List:
        """Parse settings.json.  Flag the 'env' key as a credential risk.
        Artifact type: config."""
        results = []  # type: List[Any]
        path = os.path.join(self._root, "settings.json")
        if not os.path.isfile(path):
            return results

        data = self._safe_read_json(path)
        if data is None:
            return results

        fmeta = self._file_metadata(path)
        file_hash = self._hash_file(path)

        # Check for env key (credential risk)
        has_env_block = "env" in data if isinstance(data, dict) else False
        env_keys = []  # type: List[str]
        if has_env_block and isinstance(data.get("env"), dict):
            env_keys = list(data["env"].keys())
            # Redact the env values before storing
            sanitized_data = dict(data)
            sanitized_data["env"] = {k: "[REDACTED]" for k in env_keys}
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
                "has_env_block": has_env_block,
                "env_variable_names": env_keys,
                "credential_risk": has_env_block,
                "security_note": "env block contains environment variables that may include API keys"
                if has_env_block else None,
            },
        ))

        return results

    # ------------------------------------------------------------------
    # 4. stats-cache.json -- daily activity / model usage analytics
    # ------------------------------------------------------------------
    def _collect_stats(self) -> List:
        """Parse stats-cache.json for daily activity and model usage.
        Artifact type: analytics."""
        results = []  # type: List[Any]
        path = os.path.join(self._root, "stats-cache.json")
        if not os.path.isfile(path):
            return results

        data = self._safe_read_json(path)
        if data is None:
            return results

        fmeta = self._file_metadata(path)
        file_hash = self._hash_file(path)

        # Extract summary statistics
        summary = {}  # type: Dict[str, Any]
        if isinstance(data, dict):
            summary["total_keys"] = len(data)
            # Look for model usage and daily stats patterns
            model_usage = {}  # type: Dict[str, Any]
            daily_activity = {}  # type: Dict[str, Any]
            for key, value in data.items():
                if "model" in key.lower():
                    model_usage[key] = value
                if "daily" in key.lower() or "day" in key.lower():
                    daily_activity[key] = value
            if model_usage:
                summary["model_usage"] = model_usage
            if daily_activity:
                summary["daily_activity"] = daily_activity

        results.append(self._make_artifact(
            artifact_type="analytics",
            file_path=path,
            file_hash_sha256=file_hash,
            file_size_bytes=fmeta.get("file_size_bytes"),
            file_modified=fmeta.get("file_modified"),
            file_created=fmeta.get("file_created"),
            content_preview=self._content_preview(json.dumps(data)),
            raw_data=json.dumps(data),
            metadata=summary,
        ))

        return results

    # ------------------------------------------------------------------
    # 5. plans/*.md -- plans
    # ------------------------------------------------------------------
    def _collect_plans(self) -> List:
        """Walk plans/*.md.  Artifact type: plan."""
        results = []  # type: List[Any]
        plans_dir = os.path.join(self._root, "plans")
        if not os.path.isdir(plans_dir):
            return results

        for fname in os.listdir(plans_dir):
            if not fname.endswith(".md"):
                continue
            fpath = os.path.join(plans_dir, fname)
            if os.path.islink(fpath) or not os.path.isfile(fpath):
                continue

            fmeta = self._file_metadata(fpath)
            file_hash = self._hash_file(fpath)
            text = self._safe_read_text(fpath)

            results.append(self._make_artifact(
                artifact_type="plan",
                file_path=fpath,
                file_hash_sha256=file_hash,
                file_size_bytes=fmeta.get("file_size_bytes"),
                file_modified=fmeta.get("file_modified"),
                file_created=fmeta.get("file_created"),
                content_preview=self._content_preview(text or ""),
                token_estimate=self._estimate_tokens(text or ""),
                metadata={
                    "plan_name": fname,
                },
            ))

        return results

    # ------------------------------------------------------------------
    # 6. tasks/ and teams/ -- task and team data
    # ------------------------------------------------------------------
    def _collect_tasks_teams(self) -> List:
        """Walk tasks/ and teams/ directories.
        Types: task_data, team_data."""
        results = []  # type: List[Any]
        results.extend(self._walk_json_dir(
            os.path.join(self._root, "tasks"),
            artifact_type="task_data",
        ))
        results.extend(self._walk_json_dir(
            os.path.join(self._root, "teams"),
            artifact_type="team_data",
        ))
        return results

    def _walk_json_dir(self, directory: str, artifact_type: str) -> List:
        """Walk a directory and collect JSON files as artifacts."""
        results = []  # type: List[Any]
        if not os.path.isdir(directory):
            return results

        for dirpath, _dirnames, filenames in os.walk(directory):
            for fname in filenames:
                fpath = os.path.join(dirpath, fname)
                if os.path.islink(fpath) or not os.path.isfile(fpath):
                    continue

                fmeta = self._file_metadata(fpath)
                file_hash = self._hash_file(fpath)

                # Try reading as JSON; fall back to text
                data = self._safe_read_json(fpath)
                if data is not None:
                    preview_text = json.dumps(data)
                else:
                    text = self._safe_read_text(fpath)
                    preview_text = text or ""

                results.append(self._make_artifact(
                    artifact_type=artifact_type,
                    file_path=fpath,
                    file_hash_sha256=file_hash,
                    file_size_bytes=fmeta.get("file_size_bytes"),
                    file_modified=fmeta.get("file_modified"),
                    file_created=fmeta.get("file_created"),
                    content_preview=self._content_preview(preview_text),
                    metadata={
                        "filename": fname,
                        "relative_path": os.path.relpath(fpath, self._root),
                    },
                ))

        return results

    # ------------------------------------------------------------------
    # 7. debug/*.txt -- debug logs
    # ------------------------------------------------------------------
    def _collect_debug_logs(self) -> List:
        """Walk debug/*.txt.  Artifact type: debug_log."""
        results = []  # type: List[Any]
        debug_dir = os.path.join(self._root, "debug")
        if not os.path.isdir(debug_dir):
            return results

        for fname in os.listdir(debug_dir):
            if not fname.endswith(".txt"):
                continue
            fpath = os.path.join(debug_dir, fname)
            if os.path.islink(fpath) or not os.path.isfile(fpath):
                continue

            fmeta = self._file_metadata(fpath)
            file_hash = self._hash_file(fpath)
            text = self._safe_read_text(fpath)

            results.append(self._make_artifact(
                artifact_type="debug_log",
                file_path=fpath,
                file_hash_sha256=file_hash,
                file_size_bytes=fmeta.get("file_size_bytes"),
                file_modified=fmeta.get("file_modified"),
                file_created=fmeta.get("file_created"),
                content_preview=self._content_preview(text or ""),
                token_estimate=self._estimate_tokens(text or ""),
                metadata={
                    "log_filename": fname,
                },
            ))

        return results
