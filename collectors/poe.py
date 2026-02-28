"""Poe (Quora) artifact collector."""

import os
from typing import Any, List

from collectors.base import AbstractCollector
from collectors.mixins import ElectronAppMixin
from config import HOME
from schema import AIArtifact


class PoeCollector(ElectronAppMixin, AbstractCollector):
    """Collect artifacts from the Poe desktop Electron application.

    Artifact root: ~/Library/Application Support/com.quora.poe.electron/
    Collects Electron storage (Session Storage, Local Storage, IndexedDB)
    and preferences.
    """

    def __init__(self) -> None:
        super().__init__()
        self._root = os.path.join(
            HOME, "Library", "Application Support", "com.quora.poe.electron",
        )

    @property
    def name(self) -> str:
        return "poe"

    def detect(self) -> bool:
        return os.path.isdir(self._root)

    def collect(self) -> List[AIArtifact]:
        if not os.path.isdir(self._root):
            return []

        artifacts = []  # type: List[Any]
        artifacts.extend(self._collect_electron_preferences(self._root))
        artifacts.extend(self._collect_electron_local_storage(self._root))
        artifacts.extend(self._collect_electron_session_storage(self._root))
        artifacts.extend(self._collect_electron_indexed_db(self._root))
        return artifacts
