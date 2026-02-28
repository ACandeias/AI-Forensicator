"""Collector for ChatGPT macOS app artifacts (~/Library/Group Containers/group.com.openai.chat/)."""

import os
from typing import Any, List

from collectors.base import AbstractCollector
from collectors.mixins import OpenAIDataMixin
from config import ARTIFACT_PATHS


class ChatGPTCollector(OpenAIDataMixin, AbstractCollector):
    """Collect artifacts from the ChatGPT macOS application.

    Artifact root: ~/Library/Group Containers/group.com.openai.chat/
    NOTE: .data files are CK-encrypted binary -- we collect metadata only
    (file count, sizes, timestamps), NOT content.
    """

    def __init__(self) -> None:
        super().__init__()
        self._root = ARTIFACT_PATHS["chatgpt"]

    @property
    def name(self) -> str:
        return "ChatGPT"

    def detect(self) -> bool:
        return os.path.isdir(self._root)

    def collect(self) -> List:
        artifacts = []  # type: List[Any]
        artifacts.extend(self._collect_encrypted_conversations())
        artifacts.extend(self._collect_preferences())
        return artifacts

    # ------------------------------------------------------------------
    # 1. .data files -- CK-encrypted binary (metadata only)
    # ------------------------------------------------------------------
    def _collect_encrypted_conversations(self) -> List:
        """Walk the directory for .data files.  These are CK-encrypted binary
        and cannot be decrypted without CloudKit keys, so we collect metadata
        only: file count, sizes, timestamps.
        Artifact type: encrypted_conversation."""
        return self._collect_encrypted_data_files(self._root, tool_name="ChatGPT")

    # ------------------------------------------------------------------
    # 2. com.openai.chat.plist -- preferences
    # ------------------------------------------------------------------
    def _collect_preferences(self) -> List:
        """Parse com.openai.chat.plist with plistlib for user preferences.
        Artifact type: preferences."""
        results = []  # type: List[Any]

        # The plist may be in the root or in a Library/Preferences subfolder
        candidate_paths = [
            os.path.join(self._root, "com.openai.chat.plist"),
            os.path.join(
                self._root, "Library", "Preferences", "com.openai.chat.plist"
            ),
        ]

        for path in candidate_paths:
            results.extend(self._collect_plist_preferences(path, tool_name="ChatGPT"))

        return results
