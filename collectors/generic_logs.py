"""Generic log and application collector for AI-related artifacts."""

import os
import re
import subprocess
from typing import List, Set

from collectors.base import AbstractCollector
from config import HOME
from schema import AIArtifact

# Directory names that indicate AI tool data
AI_DIRECTORY_NAMES = {
    "anthropic", "openai", "claude", "cursor",
    "copilot", "chatgpt", "perplexity", "gemini",
}

# Keywords to grep for in log files
AI_LOG_KEYWORDS = [
    "anthropic",
    "openai",
    "gpt-4",
    "claude",
    "copilot",
]

# Known AI application names for system_profiler matching
AI_APP_NAMES = [
    "claude", "chatgpt", "cursor", "copilot",
    "perplexity", "gemini", "arc",
]

# Directories to walk
SCAN_DIRS = [
    os.path.join(HOME, "Library", "Logs"),
    os.path.join(HOME, "Library", "Caches"),
    os.path.join(HOME, "Library", "Application Support"),
]

# Log file extensions to grep
LOG_EXTENSIONS = {".log", ".txt", ".jsonl", ".json"}

# Compiled keyword pattern for searching log content
_KEYWORD_PATTERN = re.compile(
    "|".join(re.escape(kw) for kw in AI_LOG_KEYWORDS),
    re.IGNORECASE,
)


class GenericLogsCollector(AbstractCollector):
    """Scan ~/Library for AI-related logs, directories, and installed apps."""

    @property
    def name(self) -> str:
        return "generic_logs"

    def detect(self) -> bool:
        # Always attempt collection; the scan itself determines what exists.
        return True

    def collect(self) -> List[AIArtifact]:
        artifacts = []  # type: List[AIArtifact]

        # Phase 1: Walk directories for AI-related subdirectories and log files
        seen_dirs = set()  # type: Set[str]
        seen_files = set()  # type: Set[str]

        for scan_root in SCAN_DIRS:
            if not os.path.isdir(scan_root):
                continue
            self._walk_directory(scan_root, artifacts, seen_dirs, seen_files)

        # Phase 2: Installed AI applications via system_profiler
        self._collect_installed_apps(artifacts)

        return artifacts

    def _walk_directory(
        self,
        root: str,
        artifacts: List[AIArtifact],
        seen_dirs: Set[str],
        seen_files: Set[str],
    ) -> None:
        """Walk a directory tree looking for AI-related dirs and log files."""
        try:
            for dirpath, dirnames, filenames in os.walk(root):
                # Skip symlinked directories
                if os.path.islink(dirpath):
                    dirnames.clear()
                    continue
                # Check if this directory name is AI-related
                dir_basename = os.path.basename(dirpath).lower()
                if dir_basename in AI_DIRECTORY_NAMES and dirpath not in seen_dirs:
                    seen_dirs.add(dirpath)
                    fmeta = self._file_metadata(dirpath)
                    artifacts.append(self._make_artifact(
                        artifact_type="ai_directory",
                        file_path=dirpath,
                        file_modified=fmeta.get("file_modified"),
                        file_created=fmeta.get("file_created"),
                        content_preview="AI-related directory: {}".format(dirpath),
                        metadata={"directory_name": dir_basename},
                    ))

                # Grep log files in AI-related directories for keywords
                if dir_basename in AI_DIRECTORY_NAMES:
                    for fname in filenames:
                        ext = os.path.splitext(fname)[1].lower()
                        if ext not in LOG_EXTENSIONS:
                            continue
                        fpath = os.path.join(dirpath, fname)
                        if os.path.islink(fpath) or fpath in seen_files:
                            continue
                        seen_files.add(fpath)
                        self._grep_log_file(fpath, artifacts)

                # Also check top-level log files for keyword matches
                for fname in filenames:
                    ext = os.path.splitext(fname)[1].lower()
                    if ext not in LOG_EXTENSIONS:
                        continue
                    fpath = os.path.join(dirpath, fname)
                    if os.path.islink(fpath) or fpath in seen_files:
                        continue
                    # Only grep files outside AI dirs if the filename hints at AI
                    fname_lower = fname.lower()
                    if any(kw in fname_lower for kw in AI_LOG_KEYWORDS):
                        seen_files.add(fpath)
                        self._grep_log_file(fpath, artifacts)

                # Limit recursion depth to avoid excessive scanning
                depth = dirpath.replace(root, "").count(os.sep)
                if depth >= 3:
                    dirnames.clear()
        except (OSError, IOError):
            pass

    def _grep_log_file(self, fpath: str, artifacts: List[AIArtifact]) -> None:
        """Search a log file for AI-related keywords and create artifacts."""
        text = self._safe_read_text(fpath)
        if text is None:
            return

        matches = _KEYWORD_PATTERN.findall(text)
        if not matches:
            return

        # Deduplicate matched keywords
        unique_keywords = sorted(set(kw.lower() for kw in matches))

        fmeta = self._file_metadata(fpath)
        preview = self._content_preview(
            "Log contains AI keywords: {}".format(", ".join(unique_keywords))
        )

        artifacts.append(self._make_artifact(
            artifact_type="log_entry",
            file_path=fpath,
            file_size_bytes=fmeta.get("file_size_bytes"),
            file_modified=fmeta.get("file_modified"),
            file_created=fmeta.get("file_created"),
            file_hash_sha256=self._hash_file(fpath),
            content_preview=preview,
            metadata={
                "matched_keywords": unique_keywords,
                "match_count": len(matches),
            },
        ))

    def _collect_installed_apps(self, artifacts: List[AIArtifact]) -> None:
        """Run system_profiler to find installed AI applications."""
        try:
            result = subprocess.run(
                ["system_profiler", "SPApplicationsDataType"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0:
                return
            output = result.stdout
        except (OSError, subprocess.TimeoutExpired):
            return

        # Parse system_profiler output: each app block starts with the app name
        # followed by indented key: value pairs
        current_app = None  # type: str
        current_location = None  # type: str
        current_version = None  # type: str

        for line in output.splitlines():
            stripped = line.strip()
            if not stripped:
                continue

            # App name lines end with ':'  and are not indented much
            if stripped.endswith(":") and not stripped.startswith("Location:"):
                # Emit previous app if it matched
                if current_app is not None:
                    self._emit_app_artifact(
                        current_app, current_location, current_version, artifacts
                    )
                current_app = stripped.rstrip(":")
                current_location = None
                current_version = None
            elif stripped.startswith("Location:"):
                current_location = stripped.split(":", 1)[1].strip()
            elif stripped.startswith("Version:"):
                current_version = stripped.split(":", 1)[1].strip()

        # Don't forget the last app
        if current_app is not None:
            self._emit_app_artifact(
                current_app, current_location, current_version, artifacts
            )

    def _emit_app_artifact(
        self,
        app_name: str,
        location: str,
        version: str,
        artifacts: List[AIArtifact],
    ) -> None:
        """Create an artifact if the app name matches an AI application."""
        app_lower = app_name.lower()
        if not any(ai_name in app_lower for ai_name in AI_APP_NAMES):
            return

        preview = "Installed AI app: {}".format(app_name)
        if version:
            preview += " v{}".format(version)

        metadata = {
            "app_name": app_name,
            "version": version,
            "location": location,
        }

        artifacts.append(self._make_artifact(
            artifact_type="installed_app",
            file_path=location,
            content_preview=self._content_preview(preview),
            metadata=metadata,
        ))
