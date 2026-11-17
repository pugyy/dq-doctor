# Configuration (1.0)

`.dqdoctor.yml` holds **datasource aliases** only. Rules live in the
contract file (`contract.yml`) where they are versioned, reviewable and
exportable.

```yaml
# .dqdoctor.yml
datasources:
  prod: postgresql://user:pass@host:5432/db?schema=analytics
  stage: mysql://user:pass@host:3306/db
  local: demo.duckdb
  exports: exports/2026-11/
default: local
```

Create it with `dqdoctor init` (refuses to overwrite without `--force`).

## Resolution order

For every command taking `--db`:

1. explicit `--db` (or the contract's `datasource:` when `--db` is absent);
2. the alias/URL/path is looked up in `datasources:`;
3. the resolved value is parsed as one of:

| Form | Backend |
|---|---|
| `*.duckdb`, `*.db`, `*.ddb`, or an existing bare name | DuckDB file |
| `.csv`, `.tsv`, `.parquet`, `.json`, `.jsonl`, `.ndjson` | DuckDB views over files |
| a directory containing those files | DuckDB views (one per file) |
| `postgresql://` / `postgres://` | PostgreSQL |
| `mysql://` / `mysql+pymysql://` | MySQL (PyMySQL) |

Anything else exits `2` with a diagnostic naming the supported forms.

## Explicit flags beat config

A `--db` on the command line always wins over `datasources.default` and
over the contract's `datasource:` field. A `--config` pointing at a missing
file, or a rules file that cannot be parsed, is a hard error (exit `2`) -
not a silent fallback.

## PostgreSQL schema

```bash
dqdoctor check --db "postgresql://user:pass@host/db?schema=analytics"
```

The schema is applied as `search_path` for profiling and as the
`information_schema` filter for metadata; FK metadata is read from the same
schema.

## MySQL

```bash
dqdoctor check --db "mysql://user:pass@host:3306/db"
```

`mysql://` is normalized to `mysql+pymysql://` because the `[sql]` extra
installs PyMySQL. Add `?schema=other` to target another database; it is
folded into the URL database segment.

## Credentials

Connection URLs are redacted (`user:***@host/db`) in every report, log
message and error. Passwords never reach JSON, HTML, JUnit or LLM payloads.

## Migrating a 0.7 config

```bash
dqdoctor migrate --in .dqdoctor.yml --out contract.yml
```

The old `tables:` / `disable_rules:` / `severity:` / `sql_rules:` /
`freshness:` sections become contract rules; disabled entries stay disabled
in the contract. See [migration-1.0.md](migration-1.0.md).
