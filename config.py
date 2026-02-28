"""AIFT configuration: paths, constants, and patterns."""

import os
import re
from typing import Dict, List

VERSION = "0.2.0"
APP_NAME = "AIFT - AI Forensics Tool"

# Database
DB_DIR = os.path.expanduser("~/.ai-forensics")
DB_PATH = os.path.join(DB_DIR, "aift.db")

# Content limits
CONTENT_PREVIEW_MAX = 500
MAX_FILE_READ_BYTES = 50 * 1024 * 1024  # 50 MB safety limit

# Security: credential patterns to redact
CREDENTIAL_PATTERNS = [
    re.compile(r'sk-[a-zA-Z0-9_-]{20,}'),          # Anthropic/OpenAI API keys
    re.compile(r'key-[a-zA-Z0-9_-]{20,}'),          # Generic API keys
    re.compile(r'ghp_[a-zA-Z0-9]{36,}'),             # GitHub personal tokens
    re.compile(r'gho_[a-zA-Z0-9]{36,}'),             # GitHub OAuth tokens
    re.compile(r'Bearer\s+[a-zA-Z0-9._-]{20,}'),    # Bearer tokens
    re.compile(r'token["\s:=]+[a-zA-Z0-9._-]{20,}', re.IGNORECASE),
    re.compile(r'password["\s:=]+\S+', re.IGNORECASE),
    re.compile(r'secret["\s:=]+\S+', re.IGNORECASE),
    re.compile(r'AKIA[0-9A-Z]{16}'),                 # AWS access key IDs
    re.compile(r'sk_live_[a-zA-Z0-9]{20,}'),         # Stripe secret keys
    re.compile(r'pk_live_[a-zA-Z0-9]{20,}'),         # Stripe publishable keys
    re.compile(r'xoxb-[a-zA-Z0-9-]{20,}'),           # Slack bot tokens
    re.compile(r'xoxp-[a-zA-Z0-9-]{20,}'),           # Slack user tokens
    re.compile(r'github_pat_[a-zA-Z0-9_]{22,}'),      # GitHub fine-grained tokens
    re.compile(r'glpat-[a-zA-Z0-9\-]{20,}'),           # GitLab personal tokens
    re.compile(r'AIza[0-9A-Za-z\-_]{35}'),             # Google Cloud API keys
    re.compile(r'npm_[a-zA-Z0-9]{36}'),                # npm tokens
    re.compile(r'pypi-[a-zA-Z0-9\-_]{16,}'),           # PyPI tokens
    re.compile(r'eyJ[a-zA-Z0-9_-]+\.eyJ[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+'),  # JWT tokens
    re.compile(r'-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----'),  # SSH private keys
    re.compile(r'(?=[a-fA-F0-9]*[a-fA-F])(?=[a-fA-F0-9]*[0-9])[a-fA-F0-9]{40,}'),  # Long hex tokens (mixed digits+letters, 40+ chars)
    re.compile(r'(?=[A-Za-z0-9+/]*[A-Z])(?=[A-Za-z0-9+/]*[a-z])(?=[A-Za-z0-9+/]*[0-9])[A-Za-z0-9+/]{40,}={0,2}'),  # Long base64 tokens (mixed case+digits, 40+ chars)
]

# Files that should never have content extracted
CREDENTIAL_FILES = {
    '.env', '.env.local', '.env.production', '.env.development',
    '.env.staging', '.env.test',
    'credentials.json', 'auth.json', 'hosts.yml', '.netrc',
    '.npmrc', '.pypirc', 'token', 'token.json',
    'service-account.json', 'keyfile.json',
    'id_rsa', 'id_ed25519', 'id_ecdsa',
}

# Artifact source paths
HOME = os.path.expanduser("~")
ARTIFACT_PATHS = {
    "claude_code": os.path.join(HOME, ".claude"),
    "claude_desktop": os.path.join(HOME, "Library", "Application Support", "Claude"),
    "chatgpt": os.path.join(HOME, "Library", "Group Containers", "group.com.openai.chat"),
    "cursor": os.path.join(HOME, "Library", "Application Support", "Cursor"),
    "chrome": os.path.join(HOME, "Library", "Application Support", "Google", "Chrome"),
    "safari_history": os.path.join(HOME, "Library", "Safari", "History.db"),
    "arc": os.path.join(HOME, "Library", "Application Support", "Arc"),
    "perplexity": os.path.join(HOME, "Library", "Application Support", "Perplexity"),
    "codex": os.path.join(HOME, ".codex"),
    "copilot": os.path.join(HOME, "Library", "Application Support", "GitHub Copilot"),
    "vscode": os.path.join(HOME, "Library", "Application Support", "Code"),
    # --- Phase 2: High-value ---
    "openai_atlas": os.path.join(HOME, "Library", "Application Support", "com.openai.atlas"),
    "lm_studio": os.path.join(HOME, ".lmstudio"),
    "cagent": os.path.join(HOME, ".cagent"),

    # --- Phase 3: Browsers ---
    "brave": os.path.join(HOME, "Library", "Application Support", "BraveSoftware", "Brave-Browser"),
    "edge": os.path.join(HOME, "Library", "Application Support", "Microsoft Edge"),

    # --- Phase 4: VS Code extensions ---
    "tabnine": os.path.join(HOME, "Library", "Application Support", "TabNine"),

    # --- Phase 5: CLI assistants ---
    "windsurf": os.path.join(HOME, "Library", "Application Support", "Windsurf"),
    "codeium": os.path.join(HOME, ".codeium"),
    "continue_dev": os.path.join(HOME, ".continue"),
    "aider": os.path.join(HOME, ".aider"),
    "amazon_q": os.path.join(HOME, ".aws", "amazonq"),
    "amazon_q_cli": os.path.join(HOME, ".amazonq"),
    "copilot_cli": os.path.join(HOME, ".copilot"),

    # --- Phase 6: Local LLM runners ---
    "ollama": os.path.join(HOME, ".ollama"),
    "jan": os.path.join(HOME, "jan"),
    "jan_app_support": os.path.join(HOME, "Library", "Application Support", "Jan"),
    "gpt4all": os.path.join(HOME, ".local", "share", "nomic.ai", "GPT4All"),
    "msty": os.path.join(HOME, "Library", "Application Support", "Msty"),

    # --- Phase 7: Productivity, Chat, Creative ---
    "raycast": os.path.join(HOME, "Library", "Application Support", "com.raycast.macos"),
    "notion": os.path.join(HOME, "Library", "Application Support", "Notion"),
    "poe": os.path.join(HOME, "Library", "Application Support", "com.quora.poe.electron"),
    "ms_copilot": os.path.join(HOME, "Library", "Containers", "com.microsoft.copilot"),
    "diffusionbee": os.path.join(HOME, ".diffusionbee"),
    "comfyui": os.path.join(HOME, "Library", "Application Support", "ComfyUI"),
    "draw_things": os.path.join(HOME, "Library", "Containers", "com.liuliu.draw-things"),
    "grammarly": os.path.join(HOME, "Library", "Application Support", "com.grammarly.ProjectLlama"),
    "pieces": os.path.join(HOME, "Library", "com.pieces.os"),
    "jetbrains_caches": os.path.join(HOME, "Library", "Caches", "JetBrains"),
    "warp": os.path.join(HOME, ".warp"),
    "warp_app_support": os.path.join(HOME, "Library", "Application Support", "dev.warp.Warp-Stable"),
    "perplexity_container": os.path.join(HOME, "Library", "Containers", "ai.perplexity.mac"),
    "cody_app": os.path.join(HOME, "Library", "Application Support", "com.sourcegraph.cody"),
}

# Browser AI URL patterns for filtering history
AI_URL_PATTERNS = [
    "%chat.openai.com%",
    "%chatgpt.com%",
    "%claude.ai%",
    "%anthropic.com%",
    "%bard.google.com%",
    "%gemini.google.com%",
    "%perplexity.ai%",
    "%copilot.microsoft.com%",
    "%github.com/copilot%",
    "%huggingface.co%",
    "%poe.com%",
    "%character.ai%",
    "%you.com%",
    "%phind.com%",
    "%cursor.sh%",
    "%v0.dev%",
    "%bolt.new%",
    "%replit.com%",
    "%labs.google.com%",
    # New patterns
    "%sourcegraph.com%",
    "%codeium.com%",
    "%windsurf.com%",
    "%continue.dev%",
    "%aider.chat%",
    "%lmstudio.ai%",
    "%ollama.com%",
    "%jan.ai%",
    "%gpt4all.io%",
    "%msty.app%",
    "%pieces.app%",
    "%grammarly.com%",
    "%diffusionbee.com%",
    "%comfyui.org%",
    "%raycast.com%",
    "%notion.so%",
    "%tabnine.com%",
    "%brave.com%",
]

# Model identification patterns
MODEL_PATTERNS = [
    re.compile(r'(claude-[\w.-]+)', re.IGNORECASE),
    re.compile(r'(gpt-[\w.-]+)', re.IGNORECASE),
    re.compile(r'(o[1-9]-[\w.-]+)', re.IGNORECASE),
    re.compile(r'(gemini-[\w.-]+)', re.IGNORECASE),
    re.compile(r'(llama-[\w.-]+)', re.IGNORECASE),
    re.compile(r'(mistral-[\w.-]+)', re.IGNORECASE),
    re.compile(r'(command-r[\w.-]*)', re.IGNORECASE),
    # New model patterns
    re.compile(r'(qwen[\w.-]+)', re.IGNORECASE),
    re.compile(r'(deepseek[\w.-]+)', re.IGNORECASE),
    re.compile(r'(phi-[\w.-]+)', re.IGNORECASE),
    re.compile(r'(starcoder[\w.-]+)', re.IGNORECASE),
]
