# dq-doctor

Pin a data quality contract once, then gate every new batch against it.
冻结一份数据质量契约，之后每次新数据都用同一份契约把关。

[![PyPI](https://img.shields.io/pypi/v/dq-doctor)](https://pypi.org/project/dq-doctor/)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue)](https://pypi.org/project/dq-doctor/)
[![CI](https://github.com/pugyy/dq-doctor/actions/workflows/ci.yml/badge.svg)](https://github.com/pugyy/dq-doctor/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-yellow)](LICENSE)

```bash
pip install dq-doctor

dqdoctor demo --dirty                                  # demo database with real problems
dqdoctor check --db dirty.duckdb --all-tables          # explore: findings + suggestions
dqdoctor rules-init --db dirty.duckdb --all-tables --out contract.yml
dqdoctor check --db dirty.duckdb --all-tables --rules contract.yml --ci
```

```
dirty_orders  score 88/100  pass 12  fail 1
  FAIL dirty_orders/not_null:user_id: Found 3/20 nulls in 'user_id'.
  PII  email: email (8 samples)
  ORPHAN dirty_orders.user_id -> dirty_users.user_id: 2/17 (heuristic)
```

Exit `0` when clean or within policy, `1` when the gate trips, `2` on
input/config/execution errors - errors exit `2` whether or not `--ci` is
given.

---

## Why 1.0

0.7 learned rules from the data it then checked: a `range` built from
observed min/max always passed, and a dirty value became "accepted".

1.0 separates the two:

| Mode | Command | Behaviour |
|---|---|---|
| Explore | `check` without `--rules` | everything learned from this batch is a **suggestion**; score is `n/a` |
| Pin | `rules-init` | writes an editable, versioned contract |
| Gate | `check --rules` | executes the pinned contract; nothing is re-learned |

Same contract, new batch, trustworthy verdict. Same rules file in CI, in
Airflow, in exports, over MCP.

## What it checks

| Rule | Applies to | Notes |
|---|---|---|
| `not_null` | any column | |
| `unique` | any column | non-null values only; NULL-ness belongs to `not_null` |
| `accepted_values` | enums | explicit `null_policy: ignore \| fail` |
| `range` | numeric | bounds pinned in the contract, stored precision-safe |
| `freshness` | TIMESTAMP / DATE only | naive timestamps = local wall clock |
| `regex` | text | backend-native (`regexp_matches` / `~` / `REGEXP_LIKE`) |
| `row_count` | table | `exact`, `min`, `max` |
| `cross_field` | two columns | `<`, `<=`, `>`, `>=`, `=`, `!=` |
| `sql` | operator query | read-only session, external access disabled on DuckDB, single statement, timeout, scalar contract |

Statuses are explicit: `pass`, `fail`, `skip`, `suggestion`, `error`.

## Contract

```yaml
version: 1
datasource: demo.duckdb
tables:
  orders:
    rules:
      - id: orders/not_null:order_id
        type: not_null
        column: order_id
        severity: high
      - id: orders/range:total_amount
        type: range
        column: total_amount
        params: {min: '0.00', max: '500.00'}   # strings preserve precision
        severity: medium
      - id: orders/sql:no_negatives
        type: sql
        column: '*'
        params:
          query: SELECT COUNT(*) FROM orders WHERE total_amount < 0
          expect: {mode: eq, value: 0}
        severity: high
      - id: orders/freshness:created_at
        type: freshness
        column: created_at
        params: {max_age_hours: 24}
        severity: high
        enabled: false            # disabled rules still export visibly
```

Ids are unique across the contract; two rules may share a column. Run
`dqdoctor migrate --in rules.yml --out contract.yml` for 0.7 files.

## Quality gate

```bash
dqdoctor check --db prod --all-tables --rules contract.yml \
  --out report.html --json report.json --junit junit.xml \
  --ci --max-failures 0 --fail-on high
```

- `--fail-on` selects which failures participate (lower severities are
  reported, not gated).
- `--max-failures` tolerates up to N participating failures.
- Multi-table runs aggregate first; each FK relationship is counted once.
- Referential integrity gates on every run; a baseline exempts only the
  specific relationships it recorded.
- Partial runs still emit results; the exit code reports the error.
- Execution errors exit `2` whether or not `--ci` is given.

Known failures (onboarding legacy data):

```bash
dqdoctor baseline capture --db prod --rules contract.yml --out baseline.json
dqdoctor check --db prod --all-tables --rules contract.yml --baseline baseline.json --ci
```

Known failures are exempted and shown as such. The same rule failing
**more** than recorded, or a new orphan relationship, still trips the gate.
Errors are never exempted.

## Datasources

```yaml
# .dqdoctor.yml
datasources:
  prod: postgresql://user:pass@host:5432/db?schema=analytics
  stage: mysql://user:pass@host:3306/db
  local: demo.duckdb
  exports: exports/2026-11/          # directory of CSV/Parquet/JSON files
default: local
```

```bash
dqdoctor tables --db prod
dqdoctor check  --db stage --all-tables --rules contract.yml
dqdoctor check  --db exports/orders.parquet --rules contract.yml --ci
```

CSV/TSV, Parquet, JSON/JSONL (single file or directory) are registered as
DuckDB views and go through the same rules, reports and exit codes.

## Reports

- `--out` HTML (escaped, no raw samples, fingerprinted text min/max)
- `--json` versioned outcome (redacted; `score_version` recorded)
- `--junit` for CI dashboards
- `dqdoctor serve --report report.json` - read-only web view

Connection strings are redacted everywhere. Explicit CLI flags beat config
values; a missing or malformed contract/config produces a diagnostic and
exit `2`.

**Credentials are never written to a contract.** For a URL datasource,
`rules-init` stores the redacted form and prints a warning; supply the real
URL with `--db` at check time, or register an alias:

```yaml
# .dqdoctor.yml
datasources:
  prod: postgresql://user:pass@host:5432/db   # read credentials from env in CI
default: prod
```

```bash
dqdoctor check --db prod --all-tables --rules contract.yml --ci
```

`.gitignore` covers `contract.yml`, `*.contract.yml` and `*.duckdb.bak`.

## Export

```bash
dqdoctor export --rules contract.yml --format dbt      --out schema.yml   # dbt >= 1.8 data_tests
dqdoctor export --rules contract.yml --format gx       --out suite.json   # GX 1.x suite shape
dqdoctor export --rules contract.yml --format soda     --out checks.yml   # SodaCL valid values
dqdoctor export --rules contract.yml --format deequ    --out deequ.json   # pydeequ mapping
dqdoctor export --rules contract.yml --format markdown --out dict.md
```

Disabled rules and unmappable rule types stay visible in every export.

## Schedulers and agents

```python
from dqdoctor.gate import DQDoctorOperator, run_gate, QualityGateError

DQDoctorOperator(source="prod", all_tables=True, rules_path="contract.yml",
                 max_failures=0, fail_on="high", out="report.json")

run_gate(source="prod", all_tables=True, rules_path="contract.yml")
```

`dqdoctor mcp` starts a stdio MCP server with `list_datasets`,
`profile_table`, `run_check` and `get_summary`, reusing the same engine.
Install with `pip install 'dq-doctor[mcp]'`.

## Performance

Profiling is batched: one aggregate per table plus a few extras.

| Table | Queries (1.0) | Queries (0.7) |
|---|---|---|
| 40 integer columns / 200k rows | **2** | ~160 |
| 4 columns / 1M rows | **3** | ~20 |

Text columns cost one extra `DISTINCT ... LIMIT` each because PII evidence
needs sample values; integer columns cost none. FK metadata is discovered
once per run and each relationship is checked once.

`--sample-rows` profiles a deterministic slice and is **explore-mode only**:
`check --rules` always profiles the full table, so a sample can never gate a
batch. Each column records `stats_row_count` (the denominator its counters
used), so sampled and full-table numbers cannot be mixed.

FK metadata is discovered once per run and each relationship is checked
once. `--sample-rows` profiles a deterministic slice (recorded in the
report); rule execution always scans the full table.

## Commands

```bash
dqdoctor --version
dqdoctor doctor                          # installation health
dqdoctor init [--force]                  # datasource registry
dqdoctor demo [--dirty] [--force]        # demo database
dqdoctor tables --db SRC
dqdoctor profile --db SRC --table T [--sample-rows N] [--out profile.json]
dqdoctor check --db SRC [--table T | --all-tables] [--rules C] [--ci] ...
dqdoctor rules-init --db SRC [--table T | --all-tables] --out contract.yml
dqdoctor baseline capture --db SRC --rules C --out baseline.json
dqdoctor migrate --in old.yml --out contract.yml
dqdoctor export --rules C --format F --out FILE
dqdoctor drift --old a.json --new b.json
dqdoctor serve --report report.json
dqdoctor mcp
```

## Documentation

| Doc | Contents |
|---|---|
| [Migration 0.7 → 1.0](docs/migration-1.0.md) | breaking changes, step-by-step |
| [Changelog](CHANGELOG.md) | release notes |
| [Limitations](docs/limitations.md) | verified vs unverified, approximations |
| [Configuration](docs/config.md) | datasource registry |
| [Custom SQL rules](docs/custom-sql-rules.md) | guarded SQL rules |
| [Export formats](docs/exporters.md) | targets and versions |
| [PostgreSQL / MySQL](docs/postgres-mysql.md) | connection and schema |
| [Architecture](docs/architecture.md) | engine, modules, data flow |

## Development

```bash
git clone https://github.com/pugyy/dq-doctor
cd dq-doctor
pip install -e ".[dev,sql]"
pytest tests/ -v          # 61 tests
ruff check dqdoctor/ tests/
```

Cross-backend tests need real services:

```bash
DQTEST_PG=postgresql://user:pass@host/db \
DQTEST_MYSQL=mysql://user:pass@host/db \
pytest tests/test_backends.py -v
```

## License

MIT
