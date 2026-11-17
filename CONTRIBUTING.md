# Contributing to dq-doctor

Thanks for your interest! Here's how to get started.

## Setup

```bash
git clone https://github.com/pugyy/dq-doctor.git
cd dq-doctor
python -m pip install -e ".[dev,sql,dashboard,mcp]"
```

Python **3.12+** is required.

## Development Workflow

1. Create a branch: `git checkout -b feature/my-feature`
2. Make changes
3. Run tests: `pytest tests/ -q`
4. Run lint: `ruff check dqdoctor/ tests/`
5. Commit and push
6. Open a Pull Request

## Running Tests

```bash
pytest tests/ -q    # 216 passed, 11 skipped locally (227 collected)
```

Tests use `tmp_path` / `tmp_root` fixtures for isolated DuckDB databases.
The `[sql]`, `[dashboard]` and `[mcp]` extras are needed for the full suite;
without them, those tests skip or fail explicitly.

Live PostgreSQL/MySQL tests are opt-in:

```bash
DQTEST_PG="postgresql://user:pass@host:5432/db" \
DQTEST_MYSQL="mysql://user:pass@host:3306/db" \
pytest tests/test_backends.py tests/test_live_backends.py -v --no-cov
```

## Code Style

- Python 3.12+ compatible
- `from __future__ import annotations` in all files
- `ruff check dqdoctor/ tests/` should pass with zero errors
- Keep SQL values bound; identifiers go through the quoting helpers
- New behaviour needs a regression test

## Project Structure

```
dqdoctor/          Main package
  cli.py           Typer CLI commands
  engine.py        CheckEngine, exit-code decision
  contract.py      versioned contract and migration
  profiling.py     batched table profiling
  rulecheck.py     built-in rule execution
  sqlrules.py      guarded operator SQL rules
  datasources.py   URL/path/alias resolution and connections
  outputs.py       HTML / JSON / JUnit writers
  gate.py          scheduler-facing gate runner
  mcp_server.py    stdio MCP server
  exporters/       dbt/GX/Soda/Deequ/Markdown
tests/             pytest tests
docs/              Documentation
```

See [docs/architecture.md](docs/architecture.md) for details.

## Reporting Issues

- Open an issue at https://github.com/pugyy/dq-doctor/issues
- Include: Python version, OS, command you ran, error message

## Adding a New Rule

1. Add the rule type and validation in `dqdoctor/rules.py`
2. Add the checker in `dqdoctor/rulecheck.py` and register it in `_DISPATCH`
3. Add tests under `tests/`
4. Update `README.md` and `docs/architecture.md` supported-rule tables

## Adding a New Export Format

1. Create `dqdoctor/exporters/your_format.py` with `save(contract, path)`
2. Register it in `dqdoctor/cli.py`
3. Add export tests under `tests/`
4. Update `docs/exporters.md`
