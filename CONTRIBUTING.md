# Contributing to dq-doctor

Thanks for your interest! Here's how to get started.

## Setup

```bash
git clone https://github.com/pugyy/dq-doctor.git
cd dq-doctor
pip install -e ".[dev]"
```

## Development Workflow

1. Create a branch: `git checkout -b feature/my-feature`
2. Make changes
3. Run tests: `pytest tests/ -v`
4. Run lint: `ruff check .`
5. Commit and push
6. Open a Pull Request

## Running Tests

```bash
pytest tests/ -v    # 101 tests, should all pass
```

Tests use `tmp_path` fixture for isolated DuckDB databases. No external dependencies needed.

## Code Style

- Python 3.9+ compatible
- `from __future__ import annotations` in all files
- `ruff check .` should pass with zero errors
- No comments unless explicitly necessary

## Project Structure

```
dqdoctor/          Main package
  cli.py           Typer CLI commands
  models.py        Pydantic data models
  profiler.py      Table profiling
  rule_engine.py   Rule generation
  validator.py     Rule validation
  reporters.py     HTML report
  connectors/      Database connectors
  exporters/       Export to dbt/GX/Soda/Deequ/Markdown
tests/             pytest tests
docs/              Documentation
examples/          Runnable examples
```

See [docs/architecture.md](docs/architecture.md) for details.

## Reporting Issues

- Open an issue at https://github.com/pugyy/dq-doctor/issues
- Include: Python version, OS, command you ran, error message

## Adding a New Rule

1. Add rule logic in `rule_engine.py` (generate)
2. Add validation in `validator.py` (execute)
3. Add tests in `tests/test_rule_engine.py` and `tests/test_validator.py`
4. Update `docs/architecture.md` supported rules table

## Adding a New Export Format

1. Create `dqdoctor/exporters/your_format.py`
2. Add to `_EXPORT_FORMATS` in `cli.py`
3. Add tests in `tests/test_exporters.py`
4. Update `docs/exporters.md`
