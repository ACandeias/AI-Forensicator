"""Sourcegraph Cody VS Code extension and standalone app collector."""

import os
from typing import List

from collectors.base import AbstractCollector
from collectors.mixins import VSCodeExtensionMixin
from config import HOME
from schema import AIArtifact


CODY_EXTENSION_ID = "sourcegraph.cody-ai"

# Standalone Cody app path (separate from VS Code extension)
CODY_STANDALONE_PATH = os.path.join(
    HOME, "Library", "Application Support", "com.sourcegraph.cody",
)


class CodyCollector(VSCodeExtensionMixin, AbstractCollector):
    """Collect artifacts from the Sourcegraph Cody VS Code extension
    and standalone desktop application."""

    @property
    def name(self) -> str:
        return "cody"

    def _storage_path(self) -> str:
        return self._get_extension_storage_path(CODY_EXTENSION_ID)

    def detect(self) -> bool:
        if os.path.isdir(self._storage_path()):
            return True
        if os.path.isdir(CODY_STANDALONE_PATH):
            return True
        return False

    def collect(self) -> List[AIArtifact]:
        results = []  # type: List[AIArtifact]

        # Collect VS Code extension data
        storage = self._storage_path()
        if os.path.isdir(storage):
            results.extend(self._collect_extension_json_files(storage))
            results.extend(self._collect_extension_state_vscdb(storage))

        # Collect standalone Cody app data
        if os.path.isdir(CODY_STANDALONE_PATH):
            results.extend(
                self._collect_extension_json_files(
                    CODY_STANDALONE_PATH,
                    artifact_type="standalone_app_data",
                )
            )

        return results
