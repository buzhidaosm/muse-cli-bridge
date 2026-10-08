# Contributing

The highest-value contribution is a reproducible, redacted compatibility report or a focused fix with a meaningful test.

```bash
uv sync --no-editable --group dev
uv run --no-editable pytest -q
uv run --no-editable ruff check src tests
uv build
```

Automated tests must not require account credentials. OS-specific tests can skip when their platform is unavailable. Live tests must be opt-in and use disposable projects, never an existing user's source or private data.

Do not add generated wire descriptors or copied client implementations. Cite protocol facts, standards and dependencies in PROVENANCE.md. Do not overstate safety, supported platforms, compatibility or release validation.

Keep changes small enough to review. Describe the concrete behavior, reproduction and validation. If your change affects sends, retries, job recovery, process termination, authentication or permissions, include tests for the failure path.

Respect other people and their work. No spam, star trading, fake users or unsupported claims about competitors.
