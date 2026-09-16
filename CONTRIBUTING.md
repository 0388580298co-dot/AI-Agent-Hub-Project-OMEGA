# Contributing to PROJECT OMEGA

Thank you for contributing to an open agent operating system.

## Engineering rules

1. Keep core interfaces provider-neutral.
2. Prefer async APIs for I/O-bound work.
3. Add type hints to public APIs.
4. Never introduce unrestricted host command or code execution.
5. Put credentials only in environment variables or secret managers.
6. Add tests for new runtime behavior and failure paths.
7. Keep commits focused and explain behavior changes.

## Local development

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
pytest -q
ruff check .
mypy src
```

## Pull requests

Describe the architecture impact, security implications, tests added, and any compatibility considerations. Changes to agent capabilities should include an explicit authorization model.
