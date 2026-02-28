# Contributing to AI-Forensicator

Thank you for your interest in contributing! This guide will help you get started.

## Development Setup

```bash
git clone https://github.com/ACandeias/AI-Forensicator.git
cd AI-Forensicator
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

## Adding a New Collector

1. **Create a new file** in `collectors/` (e.g., `collectors/my_tool.py`).

2. **Extend `AbstractCollector`**:
   ```python
   from collectors.base import AbstractCollector
   from config import ARTIFACT_PATHS

   class MyToolCollector(AbstractCollector):

       @property
       def name(self) -> str:
           return "My Tool"

       def detect(self) -> bool:
           return os.path.isdir(ARTIFACT_PATHS.get("my_tool", ""))

       def collect(self) -> list:
           artifacts = []
           # Use self._safe_read_json(), self._make_artifact(), etc.
           return artifacts
   ```

3. **Add the path** to `ARTIFACT_PATHS` in `config.py`.

4. **Register the collector** in `collectors/__init__.py`:
   ```python
   from collectors.my_tool import MyToolCollector
   # Add MyToolCollector() to the list in get_all_collectors()
   ```

5. **Write tests** in `tests/`.

## Code Style

- **Python 3.9+ compatibility** -- do not use `match` statements or `X | Y` union types.
- **Type annotations** -- use `typing` module types (`List`, `Dict`, `Optional`).
- **String formatting** -- use `.format()` instead of f-strings for consistency with the existing codebase.
- **No bare `except`** -- always catch specific exception types.
- **Security first** -- use `self._contains_credentials()` and `self._is_credential_file()` to filter sensitive data. Never store raw API keys, tokens, or passwords.

## Testing

All tests must pass before submitting a PR:

```bash
python3 -m pytest tests/ -v
```

- Tests use `tmp_path` and `monkeypatch` fixtures to avoid touching real data.
- Each collector should have basic tests for `detect()` and `collect()` with mocked file system paths.

## Pull Request Checklist

- [ ] All tests pass (`pytest tests/ -v`)
- [ ] New collector is registered in `collectors/__init__.py`
- [ ] Credential patterns are respected (no raw secrets in artifacts)
- [ ] Symlinks are skipped in file-walking code
- [ ] Code follows the existing style (`.format()`, type annotations)

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
