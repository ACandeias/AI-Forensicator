"""AIFT configuration: paths, constants, and patterns."""

import os
import re
from typing import Dict, List

VERSION = "0.1.0"
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
    re.compile(r'(?=[a-fA-F0-9]*[a-fA-F])(?=[a-fA-F0-9]*[0-9])[a-fA-F0-9]{40,}'),  # Long hex tokens (mixed digits+letters, 40+ chars)
    re.compile(r'(?=[A-Za-z0-9+/]*[A-Z])(?=[A-Za-z0-9+/]*[a-z])(?=[A-Za-z0-9+/]*[0-9])[A-Za-z0-9+/]{40,}={0,2}'),  # Long base64 tokens (mixed case+digits, 40+ chars)
]

# Files that should never have content extracted
CREDENTIAL_FILES = {
    '.env', '.env.local', '.env.production', '.env.development',
    'credentials.json', 'auth.json', 'hosts.yml', '.netrc',
    '.npmrc', '.pypirc', 'token', 'token.json',
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
]
