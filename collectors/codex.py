"""OpenAI Codex CLI artifact collector (stub)."""

import os
from typing import List

from collectors.base import AbstractCollector
from config import ARTIFACT_PATHS
from schema import AIArtifact


class CodexCollector(AbstractCollector):
    """Stub collector for OpenAI Codex CLI artifacts."""

    @property
    def name(self) -> str:
        return "codex"

    def detect(self) -> bool:
        return os.path.exists(ARTIFACT_PATHS["codex"])

    def collect(self) -> List[AIArtifact]:
        return []
