"""Perplexity artifact collector (stub)."""

import os
from typing import List

from collectors.base import AbstractCollector
from config import ARTIFACT_PATHS
from schema import AIArtifact


class PerplexityCollector(AbstractCollector):
    """Stub collector for Perplexity AI desktop application artifacts."""

    @property
    def name(self) -> str:
        return "perplexity"

    def detect(self) -> bool:
        return os.path.exists(ARTIFACT_PATHS["perplexity"])

    def collect(self) -> List[AIArtifact]:
        return []
