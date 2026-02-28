"""Supermaven VS Code extension collector."""

import os
from typing import List

from collectors.base import AbstractCollector
from collectors.mixins import VSCodeExtensionMixin
from schema import AIArtifact


SUPERMAVEN_EXTENSION_ID = "supermaven.supermaven"


class SupermavenCollector(VSCodeExtensionMixin, AbstractCollector):
    """Collect artifacts from the Supermaven VS Code extension."""

    @property
    def name(self) -> str:
        return "supermaven"

    def _storage_path(self) -> str:
        return self._get_extension_storage_path(SUPERMAVEN_EXTENSION_ID)

    def detect(self) -> bool:
        return os.path.isdir(self._storage_path())

    def collect(self) -> List[AIArtifact]:
        storage = self._storage_path()
        if not os.path.isdir(storage):
            return []

        results = []  # type: List[AIArtifact]

        # Collect extension JSON/YAML files
        results.extend(self._collect_extension_json_files(storage))

        # Collect state.vscdb if present
        results.extend(self._collect_extension_state_vscdb(storage))

        return results
