"""Collector registry: discover and instantiate all collectors."""

from typing import List

from collectors.base import AbstractCollector


def get_all_collectors() -> List[AbstractCollector]:
    """Instantiate all known collectors."""
    # --- Core AI tools ---
    from collectors.claude_code import ClaudeCodeCollector
    from collectors.claude_desktop import ClaudeDesktopCollector
    from collectors.openai_chatgpt import ChatGPTCollector
    from collectors.cursor import CursorCollector
    from collectors.browser import ChromeCollector, SafariCollector, ArcCollector
    from collectors.generic_logs import GenericLogsCollector

    # --- Phase 2: High-value ---
    from collectors.openai_atlas import OpenAIAtlasCollector
    from collectors.lm_studio import LMStudioCollector
    from collectors.codex import CodexCollector
    from collectors.copilot import CopilotCollector
    from collectors.perplexity import PerplexityCollector
    from collectors.cagent import CagentCollector

    # --- Phase 3: Browsers ---
    from collectors.brave import BraveCollector
    from collectors.edge import EdgeCollector

    # --- Phase 4: VS Code extensions ---
    from collectors.cline import ClineCollector
    from collectors.roo_code import RooCodeCollector
    from collectors.supermaven import SupermavenCollector
    from collectors.cody import CodyCollector
    from collectors.tabnine import TabnineCollector

    # --- Phase 5: CLI assistants ---
    from collectors.windsurf import WindsurfCollector
    from collectors.continue_dev import ContinueDevCollector
    from collectors.aider import AiderCollector
    from collectors.amazon_q import AmazonQCollector
    from collectors.copilot_cli import CopilotCLICollector

    # --- Phase 6: Local LLM runners ---
    from collectors.ollama import OllamaCollector
    from collectors.jan import JanCollector
    from collectors.gpt4all import GPT4AllCollector
    from collectors.msty import MstyCollector

    # --- Phase 7: Productivity, Chat, Creative ---
    from collectors.raycast import RaycastCollector
    from collectors.notion import NotionCollector
    from collectors.poe import PoeCollector
    from collectors.ms_copilot import MSCopilotCollector
    from collectors.diffusionbee import DiffusionBeeCollector
    from collectors.comfyui import ComfyUICollector
    from collectors.draw_things import DrawThingsCollector
    from collectors.grammarly import GrammarlyCollector
    from collectors.pieces import PiecesCollector
    from collectors.jetbrains_ai import JetBrainsAICollector
    from collectors.warp import WarpCollector

    return [
        # Core
        ClaudeCodeCollector(),
        ClaudeDesktopCollector(),
        ChatGPTCollector(),
        CursorCollector(),
        ChromeCollector(),
        SafariCollector(),
        ArcCollector(),
        GenericLogsCollector(),
        # Phase 2: High-value
        OpenAIAtlasCollector(),
        LMStudioCollector(),
        CodexCollector(),
        CopilotCollector(),
        PerplexityCollector(),
        CagentCollector(),
        # Phase 3: Browsers
        BraveCollector(),
        EdgeCollector(),
        # Phase 4: VS Code extensions
        ClineCollector(),
        RooCodeCollector(),
        SupermavenCollector(),
        CodyCollector(),
        TabnineCollector(),
        # Phase 5: CLI assistants
        WindsurfCollector(),
        ContinueDevCollector(),
        AiderCollector(),
        AmazonQCollector(),
        CopilotCLICollector(),
        # Phase 6: Local LLM runners
        OllamaCollector(),
        JanCollector(),
        GPT4AllCollector(),
        MstyCollector(),
        # Phase 7: Productivity, Chat, Creative
        RaycastCollector(),
        NotionCollector(),
        PoeCollector(),
        MSCopilotCollector(),
        DiffusionBeeCollector(),
        ComfyUICollector(),
        DrawThingsCollector(),
        GrammarlyCollector(),
        PiecesCollector(),
        JetBrainsAICollector(),
        WarpCollector(),
    ]


def get_detected_collectors() -> List[AbstractCollector]:
    """Return only collectors that detect artifacts on this system."""
    return [c for c in get_all_collectors() if c.detect()]
