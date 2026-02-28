"""Collector registry: discover and instantiate all collectors."""

from typing import List

from collectors.base import AbstractCollector


def get_all_collectors() -> List[AbstractCollector]:
    """Instantiate all known collectors."""
    from collectors.claude_code import ClaudeCodeCollector
    from collectors.claude_desktop import ClaudeDesktopCollector
    from collectors.openai_chatgpt import ChatGPTCollector
    from collectors.cursor import CursorCollector
    from collectors.browser import ChromeCollector, SafariCollector, ArcCollector
    from collectors.generic_logs import GenericLogsCollector
    from collectors.perplexity import PerplexityCollector
    from collectors.codex import CodexCollector
    from collectors.copilot import CopilotCollector

    return [
        ClaudeCodeCollector(),
        ClaudeDesktopCollector(),
        ChatGPTCollector(),
        CursorCollector(),
        ChromeCollector(),
        SafariCollector(),
        ArcCollector(),
        GenericLogsCollector(),
        PerplexityCollector(),
        CodexCollector(),
        CopilotCollector(),
    ]


def get_detected_collectors() -> List[AbstractCollector]:
    """Return only collectors that detect artifacts on this system."""
    return [c for c in get_all_collectors() if c.detect()]
