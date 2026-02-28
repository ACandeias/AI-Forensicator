"""Microsoft Edge browser history collector."""

import os
from typing import List

from collectors.base import AbstractCollector
from collectors.mixins import ChromiumHistoryMixin
from config import ARTIFACT_PATHS, HOME
from schema import AIArtifact


class EdgeCollector(ChromiumHistoryMixin, AbstractCollector):
    """Collect AI-related browsing history from Microsoft Edge."""

    @property
    def name(self) -> str:
        return "edge"

    def _history_path(self) -> str:
        base = ARTIFACT_PATHS.get(
            "edge",
            os.path.join(HOME, "Library", "Application Support",
                         "Microsoft Edge"),
        )
        return os.path.join(base, "Default", "History")

    def detect(self) -> bool:
        return os.path.isfile(self._history_path())

    def collect(self) -> List[AIArtifact]:
        return self._collect_chromium_history(self._history_path())
