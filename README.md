```
     _    ___ _____ _____
    / \  |_ _|  ___|_   _|
   / _ \  | || |_    | |
  / ___ \ | ||  _|   | |
 /_/   \_\___|_|     |_|

 AI Forensics Tool
```

# AI-Forensicator

**Discover, collect, and analyze forensic artifacts from AI tools on macOS.**

![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue)
![License: MIT](https://img.shields.io/badge/license-MIT-green)
![Platform: macOS](https://img.shields.io/badge/platform-macOS-lightgrey)

---

## What It Does

AIFT scans your macOS system for artifacts left behind by AI-powered tools -- conversation histories, configuration files, session data, browser activity, and more. It collects metadata and content previews into a local SQLite database for analysis, timeline reconstruction, and reporting.

### Feature Highlights

- **10+ AI tool support** -- Claude Code, Claude Desktop, ChatGPT, Cursor, Chrome/Safari/Arc AI history, and more
- **Read-only collection** -- never modifies source files; SQLite DBs opened in immutable mode
- **Credential redaction** -- API keys, tokens, and secrets are automatically detected and filtered
- **Interactive TUI** -- Rich-powered terminal interface for browsing, searching, and timeline views
- **Export formats** -- CSV, JSON, JSONL, and HTML reports
- **Extensible architecture** -- add new collectors by extending a single base class

---

## Quick Start

```bash
# Clone the repository
git clone https://github.com/ACandeias/AI-Forensicator.git
cd AI-Forensicator

# Install dependencies
pip install -r requirements.txt

# Detect available AI tools
python3 main.py collect --dry-run

# Run full collection
python3 main.py collect

# View statistics
python3 main.py stats

# Launch interactive TUI
python3 main.py
```

Or install as a package:

```bash
pip install .
aift collect --dry-run
```

---

## Screenshot / TUI Modes

When launched without a subcommand (`python3 main.py`), AIFT opens an interactive terminal UI with:

- **Dashboard** -- summary statistics, artifact counts by source, model usage
- **Browse** -- paginated artifact table with source/type filters
- **Timeline** -- chronological view of AI activity with day separators
- **Search** -- full-text search across content previews and file paths
- **Export** -- generate reports in multiple formats

---

## Architecture

```
ai_forensics/
|-- main.py                  # CLI entry point + argparse
|-- config.py                # Paths, patterns, constants
|-- schema.py                # AIArtifact + CollectionRun dataclasses
|-- db.py                    # SQLite (WAL mode) database layer
|-- normalizer.py            # Timestamp normalization, sanitization
|-- collectors/
|   |-- __init__.py          # Collector registry
|   |-- base.py              # AbstractCollector base class
|   |-- claude_code.py       # ~/.claude/ artifacts
|   |-- claude_desktop.py    # Claude Desktop Electron app
|   |-- openai_chatgpt.py    # ChatGPT macOS app
|   |-- cursor.py            # Cursor editor
|   |-- browser.py           # Chrome, Safari, Arc AI history
|   |-- generic_logs.py      # System-wide AI log scanning
|   |-- codex.py             # OpenAI Codex (stub)
|   |-- copilot.py           # GitHub Copilot (stub)
|   +-- perplexity.py        # Perplexity AI (stub)
|-- analyzers/
|   |-- stats.py             # Summary statistics
|   |-- timeline.py          # Chronological analysis
|   +-- export.py            # CSV/JSON/JSONL/HTML export
|-- ui/
|   +-- terminal.py          # Rich-based interactive TUI
+-- tests/
    |-- test_collectors.py   # Base collector unit tests
    |-- test_db.py           # Database operation tests
    +-- test_schema.py       # Data model tests
```

---

## Supported Tools

| Tool | Status | Data Collected |
|------|--------|----------------|
| Claude Code | Full | Prompt history, session conversations, settings, plans, tasks, debug logs |
| Claude Desktop | Full | MCP config, app config, session/local storage, IndexedDB, preferences, SQLite DBs |
| ChatGPT (macOS) | Full | Conversation database |
| Cursor | Full | Settings, workspace storage, state database |
| Chrome | Full | AI-related browsing history |
| Safari | Full | AI-related browsing history (requires Full Disk Access) |
| Arc | Full | AI-related browsing history |
| Generic Logs | Full | AI keyword matches in ~/Library logs, installed AI apps |
| Perplexity | Stub | Planned |
| OpenAI Codex | Stub | Planned |
| GitHub Copilot | Stub | Planned |

---

## CLI Reference

```bash
# Detection only (no collection)
python3 main.py collect --dry-run

# Full collection
python3 main.py collect
python3 main.py collect -v          # verbose logging

# Browse artifacts
python3 main.py browse
python3 main.py browse --source "Claude Code" --type conversation_message --limit 20

# Summary statistics
python3 main.py stats

# Search
python3 main.py search "query string"

# Timeline
python3 main.py timeline
python3 main.py timeline --start 2024-01-01 --end 2024-12-31 --source "Claude Code"

# Export
python3 main.py export csv output.csv
python3 main.py export json output.json
python3 main.py export jsonl output.jsonl
python3 main.py export report report.html

# Interactive TUI
python3 main.py
```

---

## Security Model

AIFT is designed for **read-only forensic collection** with built-in privacy protections:

- All SQLite databases are opened with `?immutable=1` -- no writes to source files
- Credential patterns (API keys, tokens, passwords, AWS keys, Stripe keys, Slack tokens) are automatically redacted
- OAuth token caches and MCP server environment variables are filtered
- Credential files (.env, credentials.json, etc.) are flagged but never read
- Symlinks are skipped to prevent path traversal
- File size limit of 50 MB prevents memory exhaustion

See [SECURITY.md](SECURITY.md) for full details.

---

## Contributing

We welcome contributions! See [CONTRIBUTING.md](CONTRIBUTING.md) for:

- How to add a new collector
- Code style guidelines
- Testing requirements

---

## License

MIT License -- see [LICENSE](LICENSE) for details.
