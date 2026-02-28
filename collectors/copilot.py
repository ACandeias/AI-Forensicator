"""GitHub Copilot artifact collector (stub)."""

import os
from typing import List

from collectors.base import AbstractCollector
from config import ARTIFACT_PATHS
from schema import AIArtifact


class CopilotCollector(AbstractCollector):
    """Stub collector for GitHub Copilot application artifacts."""

    @property
    def name(self) -> str:
        return "copilot"

    def detect(self) -> bool:
        return os.path.exists(ARTIFACT_PATHS["copilot"])

    def collect(self) -> List[AIArtifact]:
        return []
