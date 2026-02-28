# Security Model

AIFT (AI Forensics Tool) is designed with a **read-only, privacy-first** approach to digital forensic artifact collection.

## Design Principles

- **Read-only collection**: AIFT never modifies, deletes, or writes to any artifact source. All SQLite databases are opened with `?immutable=1`.
- **Credential redaction**: All collected content is scanned against a comprehensive set of credential patterns (API keys, tokens, passwords, secrets) and redacted before storage.
- **No key extraction**: AIFT explicitly filters out API keys, OAuth tokens, session cookies, and other authentication material. It records the *presence* of credential files, not their contents.
- **Symlink safety**: Symlinked files and directories are skipped to prevent path traversal attacks.
- **Size guards**: Files larger than 50 MB are skipped to prevent memory exhaustion.

## What IS Collected

| Data Type | Examples |
|-----------|----------|
| Configuration files | MCP server names (not env values), settings, preferences |
| Conversation metadata | Session IDs, timestamps, message roles, token estimates |
| Content previews | First 500 characters of messages (with credential redaction) |
| File metadata | Paths, SHA-256 hashes, sizes, modification dates |
| Browser history URLs | Only URLs matching known AI service domains |
| Installed applications | AI tool names, versions, install locations |
| Log file references | File paths and matched AI keywords (not full log content) |

## What is NEVER Collected

| Data Type | Details |
|-----------|---------|
| API keys / tokens | sk-*, ghp_*, Bearer tokens, AWS keys, Stripe keys, Slack tokens |
| OAuth data | Token caches, refresh tokens, session cookies |
| Passwords / secrets | Any key-value pair matching `password`, `secret`, `credential` |
| Credential files | .env, credentials.json, auth.json, .netrc, .npmrc, .pypirc |
| MCP server env values | Environment variable values in MCP server configs are redacted |
| LevelDB sensitive data | Entries containing token, auth, cookie, session, password, secret, credential, or oauth keywords |

## Permissions Required

| Permission | Purpose |
|-----------|---------|
| **File system read access** | Read AI tool data directories under `~/` and `~/Library/` |
| **Full Disk Access** (optional) | Required for Safari history (`~/Library/Safari/History.db`) due to macOS TCC protection |

AIFT does **not** require network access, root/sudo privileges, or write access to any directory other than its own database at `~/.ai-forensics/`.

## Reporting Vulnerabilities

If you discover a security vulnerability in AIFT, please report it by [opening an issue on GitHub](https://github.com/ACandeias/AI-Forensicator/issues).

1. Include: description, reproduction steps, and potential impact.
2. We will acknowledge receipt within 48 hours and aim to release a fix within 7 days.

Thank you for helping keep AIFT safe.
