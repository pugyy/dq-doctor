# PostgreSQL / MySQL (1.0)

```bash
pip install "dq-doctor[sql]"
```

The `[sql]` extra installs SQLAlchemy, psycopg2-binary and PyMySQL.

## Connect

```bash
dqdoctor check --db "postgresql://user:pass@host:5432/db" --all-tables --rules c.yml
dqdoctor check --db "mysql://user:pass@host:3306/db"      --all-tables --rules c.yml
```

`mysql://` is normalized to `mysql+pymysql://` automatically; you do not
need to write the driver prefix.

## Non-default schema

```bash
dqdoctor check --db "postgresql://user:pass@host/db?schema=analytics" ...
```

- the schema becomes the session `search_path` for profiling and rules;
- `information_schema` metadata is filtered to that schema;
- declared FK metadata is read from the same schema.

For MySQL, `?schema=other_db` selects another database (folded into the
URL database segment).

## What runs on SQL backends

| Feature | Implementation |
|---|---|
| tables / columns | `information_schema`, schema-bound parameters |
| profiling | one aggregate `SELECT` (same as DuckDB) |
| rules | native SQL: `regexp_matches` (DuckDB), `~` (PostgreSQL), `REGEXP_LIKE` (MySQL) |
| declared FKs | `information_schema.table_constraints` / `key_column_usage` |
| FK checks | NULL-safe `<=>` (MySQL) / `IS NOT DISTINCT FROM` (PostgreSQL) |
| read-only | `default_transaction_read_only=on` / `SET SESSION TRANSACTION READ ONLY` |
| SQL rule timeout | `statement_timeout` / `max_execution_time` |

## Verification status

The cross-backend suite lives in `tests/test_backends.py` and runs in CI
against real PostgreSQL 16 and MySQL 8 services. It covers:

- identical verdicts for `unique`, `accepted_values`, `range`;
- read-only sessions rejecting writes;
- SQL rule scalar contracts (`eq`, `lte`);
- declared FK direction.

Locally, this suite is skipped unless you point it at live services:

```bash
DQTEST_PG=postgresql://user:pass@host/db \
DQTEST_MYSQL=mysql://user:pass@host/db \
pytest tests/test_backends.py -v
```

## Credentials

URLs are redacted to `user:***@host/db` in all reports, logs and errors.
Prefer a read-only database user for `check` runs; dq-doctor also enforces
a read-only session where the backend supports it.
