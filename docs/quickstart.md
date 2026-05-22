# Quick Start

## Install

```bash
pip install dq-doctor
```

Optional extras:

```bash
pip install dq-doctor[sql]       # PostgreSQL / MySQL support
pip install dq-doctor[llm]       # LLM-enhanced rule suggestions
pip install dq-doctor[dashboard] # Web dashboard
```

## 30-Second Demo

```bash
# Generate a demo database with intentional issues
dqdoctor demo --dirty

# Run a full check
dqdoctor check --db dirty.duckdb --all-tables --out report.html

# Open the report
open report.html  # macOS
start report.html # Windows
```

## Core Commands

```bash
# List tables
dqdoctor tables --db demo.duckdb

# Profile a table (column stats + PII detection)
dqdoctor profile --db demo.duckdb --table orders

# Full check: profile + rules + validate + HTML report
dqdoctor check --db demo.duckdb --table orders --out report.html

# Check all tables
dqdoctor check --db demo.duckdb --all-tables --out report.html

# Export rules to dbt / GX / Soda / Deequ / Markdown
dqdoctor export --db demo.duckdb --table orders --format dbt --out schema.yml
```

## Health Check

```bash
dqdoctor doctor
```

Verifies your installation: Python version, DuckDB, report templates, optional dependencies.

## Next Steps

- [Configuration file](config.md) — persist settings in `.dqdoctor.yml`
- [Custom SQL rules](custom-sql-rules.md) — write your own validation queries
- [PostgreSQL / MySQL](postgres-mysql.md) — connect to real databases
- [Export formats](exporters.md) — integrate with dbt, Great Expectations, Soda
