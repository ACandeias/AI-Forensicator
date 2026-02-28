"""Collector for LM Studio artifacts (~/.lmstudio/).

LM Studio is a local LLM runner.  We collect settings, MCP configuration,
model inventory, download jobs, server logs, and HTTP server config.
We MUST skip the credentials/ directory and .internal/lms-key-2 entirely.
"""

import json
import os
from typing import Any, Dict, List, Optional

from collectors.base import AbstractCollector
from collectors.mixins import LocalLLMRunnerMixin
from config import ARTIFACT_PATHS, HOME
from normalizer import sanitize_content


# Directories and files that must be skipped for security
_SKIP_DIRS = {"credentials"}
_SKIP_FILES = {"lms-key-2"}


class LMStudioCollector(LocalLLMRunnerMixin, AbstractCollector):
    """Collect artifacts from the LM Studio local LLM runner.

    Artifact root: ~/.lmstudio/
    Contains settings, MCP config, model inventory, download jobs,
    server logs, and HTTP server configuration.
    SKIPS: credentials/ directory and .internal/lms-key-2.
    """

    def __init__(self) -> None:
        super().__init__()
        self._root = ARTIFACT_PATHS.get(
            "lm_studio",
            os.path.join(HOME, ".lmstudio"),
        )

    @property
    def name(self) -> str:
        return "LM Studio"

    def detect(self) -> bool:
        return os.path.isdir(self._root)

    def collect(self) -> List:
        artifacts = []  # type: List[Any]
        artifacts.extend(self._collect_settings())
        artifacts.extend(self._collect_mcp_config())
        artifacts.extend(self._collect_model_data())
        artifacts.extend(self._collect_download_jobs())
        artifacts.extend(self._collect_server_logs())
        artifacts.extend(self._collect_http_server_config())
        artifacts.extend(self._collect_models_inventory())
        return artifacts

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    def _should_skip_path(self, path: str) -> bool:
        """Check if a path falls within a skipped directory or is a skipped file."""
        basename = os.path.basename(path)
        if basename in _SKIP_FILES:
            return True
        # Check all path components for skipped directories
        parts = path.split(os.sep)
        for part in parts:
            if part in _SKIP_DIRS:
                return True
        return False

    # ------------------------------------------------------------------
    # 1. settings.json
    # ------------------------------------------------------------------
    def _collect_settings(self) -> List:
        """Parse settings.json for application configuration.
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
        sanitized = sanitize_content(json.dumps(data))

        results.append(self._make_artifact(
            artifact_type="config",
            file_path=path,
            file_hash_sha256=file_hash,
            file_size_bytes=fmeta.get("file_size_bytes"),
            file_modified=fmeta.get("file_modified"),
            file_created=fmeta.get("file_created"),
            content_preview=self._content_preview(sanitized),
            raw_data=sanitized,
            metadata={
                "config_file": "settings.json",
                "key_count": len(data) if isinstance(data, dict) else 0,
            },
        ))

        return results

    # ------------------------------------------------------------------
    # 2. mcp.json -- MCP server configuration (redact env values)
    # ------------------------------------------------------------------
    def _collect_mcp_config(self) -> List:
        """Parse mcp.json.  Redact all values inside 'env' blocks.
        Artifact type: config."""
        results = []  # type: List[Any]
        path = os.path.join(self._root, "mcp.json")
        if not os.path.isfile(path):
            return results

        data = self._safe_read_json(path)
        if data is None:
            return results

        fmeta = self._file_metadata(path)
        file_hash = self._hash_file(path)

        # Deep-redact env values
        redacted_data = self._redact_env_values(data)
        sanitized = sanitize_content(json.dumps(redacted_data))

        results.append(self._make_artifact(
            artifact_type="config",
            file_path=path,
            file_hash_sha256=file_hash,
            file_size_bytes=fmeta.get("file_size_bytes"),
            file_modified=fmeta.get("file_modified"),
            file_created=fmeta.get("file_created"),
            content_preview=self._content_preview(sanitized),
            raw_data=sanitized,
            metadata={
                "config_file": "mcp.json",
                "env_values_redacted": True,
            },
        ))

        return results

    def _redact_env_values(self, obj: Any) -> Any:
        """Recursively redact values in 'env' dict blocks."""
        if isinstance(obj, dict):
            result = {}  # type: Dict[str, Any]
            for key, value in obj.items():
                if key == "env" and isinstance(value, dict):
                    result[key] = {k: "[REDACTED]" for k in value}
                else:
                    result[key] = self._redact_env_values(value)
            return result
        if isinstance(obj, list):
            return [self._redact_env_values(item) for item in obj]
        return obj

    # ------------------------------------------------------------------
    # 3. .internal/model-data.json -- model inventory
    # ------------------------------------------------------------------
    def _collect_model_data(self) -> List:
        """Parse .internal/model-data.json for model inventory.
        Artifact type: model_inventory."""
        results = []  # type: List[Any]
        path = os.path.join(self._root, ".internal", "model-data.json")
        if not os.path.isfile(path):
            return results

        data = self._safe_read_json(path)
        if data is None:
            return results

        fmeta = self._file_metadata(path)
        file_hash = self._hash_file(path)
        sanitized = sanitize_content(json.dumps(data))

        # Summarize model entries
        model_count = 0
        if isinstance(data, list):
            model_count = len(data)
        elif isinstance(data, dict):
            model_count = len(data)

        results.append(self._make_artifact(
            artifact_type="model_inventory",
            file_path=path,
            file_hash_sha256=file_hash,
            file_size_bytes=fmeta.get("file_size_bytes"),
            file_modified=fmeta.get("file_modified"),
            file_created=fmeta.get("file_created"),
            content_preview=self._content_preview(
                "LM Studio: {} model entries in model-data.json".format(model_count)
            ),
            raw_data=sanitized if len(sanitized) < 50000 else None,
            metadata={
                "model_count": model_count,
                "source_file": "model-data.json",
            },
        ))

        return results

    # ------------------------------------------------------------------
    # 4. .internal/download-jobs-info.json -- download history
    # ------------------------------------------------------------------
    def _collect_download_jobs(self) -> List:
        """Parse .internal/download-jobs-info.json for model download history.
        Artifact type: download_history."""
        results = []  # type: List[Any]
        path = os.path.join(self._root, ".internal", "download-jobs-info.json")
        if not os.path.isfile(path):
            return results

        data = self._safe_read_json(path)
        if data is None:
            return results

        fmeta = self._file_metadata(path)
        file_hash = self._hash_file(path)
        sanitized = sanitize_content(json.dumps(data))

        job_count = 0
        if isinstance(data, list):
            job_count = len(data)
        elif isinstance(data, dict):
            job_count = len(data)

        results.append(self._make_artifact(
            artifact_type="download_history",
            file_path=path,
            file_hash_sha256=file_hash,
            file_size_bytes=fmeta.get("file_size_bytes"),
            file_modified=fmeta.get("file_modified"),
            file_created=fmeta.get("file_created"),
            content_preview=self._content_preview(
                "LM Studio: {} download jobs".format(job_count)
            ),
            raw_data=sanitized if len(sanitized) < 50000 else None,
            metadata={
                "job_count": job_count,
                "source_file": "download-jobs-info.json",
            },
        ))

        return results

    # ------------------------------------------------------------------
    # 5. server logs
    # ------------------------------------------------------------------
    def _collect_server_logs(self) -> List:
        """Collect server log files.
        Artifact type: server_log."""
        results = []  # type: List[Any]

        # Check common log locations
        log_dirs = [
            os.path.join(self._root, "server-logs"),
            os.path.join(self._root, "logs"),
            os.path.join(self._root, ".internal", "logs"),
        ]

        for log_dir in log_dirs:
            if not os.path.isdir(log_dir):
                continue

            try:
                for fname in os.listdir(log_dir):
                    fpath = os.path.join(log_dir, fname)
                    if os.path.islink(fpath) or not os.path.isfile(fpath):
                        continue
                    if self._should_skip_path(fpath):
                        continue
                    if self._is_credential_file(fpath):
                        continue

                    fmeta = self._file_metadata(fpath)
                    file_hash = self._hash_file(fpath)
                    text = self._safe_read_text(fpath)

                    results.append(self._make_artifact(
                        artifact_type="server_log",
                        file_path=fpath,
                        file_hash_sha256=file_hash,
                        file_size_bytes=fmeta.get("file_size_bytes"),
                        file_modified=fmeta.get("file_modified"),
                        file_created=fmeta.get("file_created"),
                        content_preview=self._content_preview(text or ""),
                        token_estimate=self._estimate_tokens(text or ""),
                        metadata={
                            "log_filename": fname,
                            "log_directory": os.path.basename(log_dir),
                        },
                    ))
            except OSError:
                continue

        return results

    # ------------------------------------------------------------------
    # 6. HTTP server config
    # ------------------------------------------------------------------
    def _collect_http_server_config(self) -> List:
        """Collect HTTP server configuration files.
        Artifact type: config."""
        results = []  # type: List[Any]

        config_names = [
            "http-server-config.json",
            "server-config.json",
            "api-config.json",
        ]

        for dirpath, _dirnames, filenames in os.walk(self._root):
            if os.path.islink(dirpath):
                continue
            if self._should_skip_path(dirpath):
                _dirnames[:] = []
                continue
            for fname in filenames:
                if fname not in config_names:
                    continue
                fpath = os.path.join(dirpath, fname)
                if os.path.islink(fpath) or not os.path.isfile(fpath):
                    continue

                data = self._safe_read_json(fpath)
                if data is None:
                    continue

                fmeta = self._file_metadata(fpath)
                file_hash = self._hash_file(fpath)
                sanitized = sanitize_content(json.dumps(data))

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
                        "config_file": fname,
                        "relative_path": os.path.relpath(fpath, self._root),
                    },
                ))

        return results

    # ------------------------------------------------------------------
    # 7. Model files inventory (via LocalLLMRunnerMixin)
    # ------------------------------------------------------------------
    def _collect_models_inventory(self) -> List:
        """Use the LocalLLMRunnerMixin to inventory downloaded model files."""
        results = []  # type: List[Any]
        models_dir = os.path.join(self._root, "models")
        if os.path.isdir(models_dir):
            results.extend(self._collect_model_inventory(models_dir, tool_name="LM Studio"))
        return results
