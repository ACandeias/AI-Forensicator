"""Collector for OpenAI Atlas (macOS desktop app) artifacts.

Path: ~/Library/Application Support/com.openai.atlas/
The Atlas app uses UUID-based subdirectories, CK-encrypted .data files,
binary plist tabs, and an embedded Chromium browser.
"""

import json
import os
import re
from typing import Any, Dict, List, Optional

from collectors.base import AbstractCollector
from collectors.mixins import ChromiumHistoryMixin, OpenAIDataMixin
from config import ARTIFACT_PATHS, HOME
from normalizer import sanitize_content


# UUID directory pattern
_UUID_RE = re.compile(
    r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$',
    re.IGNORECASE,
)


class OpenAIAtlasCollector(OpenAIDataMixin, ChromiumHistoryMixin, AbstractCollector):
    """Collect artifacts from the OpenAI Atlas macOS desktop application.

    Artifact root: ~/Library/Application Support/com.openai.atlas/
    Contains CK-encrypted .data files, binary plist tab data,
    embedded Chromium browser history, profile data, and analytics.
    """

    def __init__(self) -> None:
        super().__init__()
        self._root = ARTIFACT_PATHS.get(
            "openai_atlas",
            os.path.join(HOME, "Library", "Application Support", "com.openai.atlas"),
        )

    @property
    def name(self) -> str:
        return "OpenAI Atlas"

    def detect(self) -> bool:
        return os.path.isdir(self._root)

    def collect(self) -> List:
        artifacts = []  # type: List[Any]
        artifacts.extend(self._collect_encrypted_data())
        artifacts.extend(self._collect_plist_tabs())
        artifacts.extend(self._collect_browser_history())
        artifacts.extend(self._collect_profile_data())
        artifacts.extend(self._collect_statsig_analytics())
        return artifacts

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    def _discover_uuid_dirs(self) -> List[str]:
        """Walk the atlas root to find UUID-named subdirectories."""
        uuid_dirs = []  # type: List[str]
        try:
            for entry in os.listdir(self._root):
                entry_path = os.path.join(self._root, entry)
                if os.path.islink(entry_path):
                    continue
                if os.path.isdir(entry_path) and _UUID_RE.match(entry):
                    uuid_dirs.append(entry_path)
        except OSError:
            pass
        # Also check one level deeper
        try:
            for entry in os.listdir(self._root):
                subdir = os.path.join(self._root, entry)
                if os.path.islink(subdir) or not os.path.isdir(subdir):
                    continue
                try:
                    for child in os.listdir(subdir):
                        child_path = os.path.join(subdir, child)
                        if os.path.islink(child_path):
                            continue
                        if os.path.isdir(child_path) and _UUID_RE.match(child):
                            if child_path not in uuid_dirs:
                                uuid_dirs.append(child_path)
                except OSError:
                    continue
        except OSError:
            pass
        return uuid_dirs

    # ------------------------------------------------------------------
    # 1. Encrypted .data files (metadata only via mixin)
    # ------------------------------------------------------------------
    def _collect_encrypted_data(self) -> List:
        """Collect metadata for CK-encrypted .data files across all UUID dirs."""
        results = []  # type: List[Any]
        # Collect from the root and each UUID subdirectory
        results.extend(self._collect_encrypted_data_files(self._root, tool_name="OpenAI Atlas"))
        for uuid_dir in self._discover_uuid_dirs():
            results.extend(self._collect_encrypted_data_files(uuid_dir, tool_name="OpenAI Atlas"))
        return results

    # ------------------------------------------------------------------
    # 2. Binary plist tabs (tabs.plist, archived-tabs.plist)
    # ------------------------------------------------------------------
    def _collect_plist_tabs(self) -> List:
        """Parse binary plist tab files for title, URL, and date information."""
        results = []  # type: List[Any]
        plist_names = ["tabs.plist", "archived-tabs.plist"]

        for dirpath, _dirnames, filenames in os.walk(self._root):
            if os.path.islink(dirpath):
                continue
            for fname in filenames:
                if fname not in plist_names:
                    continue
                fpath = os.path.join(dirpath, fname)
                if os.path.islink(fpath) or not os.path.isfile(fpath):
                    continue

                fmeta = self._file_metadata(fpath)
                file_hash = self._hash_file(fpath)

                plist_data = self._safe_read_plist(fpath)
                if plist_data is None:
                    continue

                safe_data = self._plist_to_json_safe(plist_data)

                # Extract tab entries if the plist contains a list of tabs
                tabs = []  # type: List[Dict[str, Any]]
                if isinstance(safe_data, list):
                    for tab in safe_data:
                        if isinstance(tab, dict):
                            tabs.append({
                                "title": tab.get("title", ""),
                                "url": tab.get("url", tab.get("URL", "")),
                                "date": tab.get("date", tab.get("lastAccessDate", "")),
                            })
                elif isinstance(safe_data, dict):
                    # Some plists wrap tabs under a key
                    for key in ("tabs", "archivedTabs", "items"):
                        tab_list = safe_data.get(key)
                        if isinstance(tab_list, list):
                            for tab in tab_list:
                                if isinstance(tab, dict):
                                    tabs.append({
                                        "title": tab.get("title", ""),
                                        "url": tab.get("url", tab.get("URL", "")),
                                        "date": tab.get("date", tab.get("lastAccessDate", "")),
                                    })

                sanitized_text = sanitize_content(json.dumps(safe_data, default=str))

                results.append(self._make_artifact(
                    artifact_type="tab_data",
                    file_path=fpath,
                    file_hash_sha256=file_hash,
                    file_size_bytes=fmeta.get("file_size_bytes"),
                    file_modified=fmeta.get("file_modified"),
                    file_created=fmeta.get("file_created"),
                    content_preview=self._content_preview(sanitized_text),
                    raw_data=sanitized_text if len(sanitized_text) < 50000 else None,
                    metadata={
                        "plist_file": fname,
                        "tab_count": len(tabs),
                        "tabs": tabs[:50],
                    },
                ))

        return results

    # ------------------------------------------------------------------
    # 3. Embedded Chromium browser history
    # ------------------------------------------------------------------
    def _collect_browser_history(self) -> List:
        """Find and collect Chromium History databases embedded in Atlas."""
        results = []  # type: List[Any]

        # Search UUID dirs and common profile locations for History DB
        search_dirs = [self._root] + self._discover_uuid_dirs()
        for search_dir in search_dirs:
            db_path = self._find_chromium_history_db(search_dir)
            if db_path:
                results.extend(self._collect_chromium_history(db_path))

        return results

    # ------------------------------------------------------------------
    # 4. Profile data (JSON files with user/account info)
    # ------------------------------------------------------------------
    def _collect_profile_data(self) -> List:
        """Collect profile and account JSON files."""
        results = []  # type: List[Any]
        profile_filenames = {
            "profile.json", "user.json", "account.json",
            "preferences.json", "settings.json",
        }

        for dirpath, _dirnames, filenames in os.walk(self._root):
            if os.path.islink(dirpath):
                continue
            for fname in filenames:
                if fname not in profile_filenames:
                    continue
                fpath = os.path.join(dirpath, fname)
                if os.path.islink(fpath) or not os.path.isfile(fpath):
                    continue
                if self._is_credential_file(fpath):
                    continue

                data = self._safe_read_json(fpath)
                if data is None:
                    continue

                fmeta = self._file_metadata(fpath)
                file_hash = self._hash_file(fpath)
                sanitized = sanitize_content(json.dumps(data))

                results.append(self._make_artifact(
                    artifact_type="profile",
                    file_path=fpath,
                    file_hash_sha256=file_hash,
                    file_size_bytes=fmeta.get("file_size_bytes"),
                    file_modified=fmeta.get("file_modified"),
                    file_created=fmeta.get("file_created"),
                    content_preview=self._content_preview(sanitized),
                    raw_data=sanitized if len(sanitized) < 50000 else None,
                    metadata={
                        "filename": fname,
                        "relative_path": os.path.relpath(fpath, self._root),
                    },
                ))

        return results

    # ------------------------------------------------------------------
    # 5. Statsig analytics
    # ------------------------------------------------------------------
    def _collect_statsig_analytics(self) -> List:
        """Collect Statsig analytics/experiment data files."""
        results = []  # type: List[Any]

        for dirpath, _dirnames, filenames in os.walk(self._root):
            if os.path.islink(dirpath):
                continue
            # Look for statsig-related directories and files
            dir_basename = os.path.basename(dirpath).lower()
            for fname in filenames:
                if "statsig" not in fname.lower() and "statsig" not in dir_basename:
                    continue
                if not (fname.endswith(".json") or fname.endswith(".plist")):
                    continue
                fpath = os.path.join(dirpath, fname)
                if os.path.islink(fpath) or not os.path.isfile(fpath):
                    continue

                fmeta = self._file_metadata(fpath)
                file_hash = self._hash_file(fpath)

                if fname.endswith(".plist"):
                    plist_data = self._safe_read_plist(fpath)
                    if plist_data is None:
                        continue
                    safe_data = self._plist_to_json_safe(plist_data)
                    text = json.dumps(safe_data, default=str)
                else:
                    data = self._safe_read_json(fpath)
                    if data is None:
                        continue
                    text = json.dumps(data)

                sanitized = sanitize_content(text)

                results.append(self._make_artifact(
                    artifact_type="analytics",
                    file_path=fpath,
                    file_hash_sha256=file_hash,
                    file_size_bytes=fmeta.get("file_size_bytes"),
                    file_modified=fmeta.get("file_modified"),
                    file_created=fmeta.get("file_created"),
                    content_preview=self._content_preview(sanitized),
                    raw_data=sanitized if len(sanitized) < 50000 else None,
                    metadata={
                        "filename": fname,
                        "relative_path": os.path.relpath(fpath, self._root),
                        "analytics_provider": "statsig",
                    },
                ))

        return results
