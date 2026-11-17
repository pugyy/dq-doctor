# Migrating from 0.7 to 1.0

dq-doctor 1.0 is a breaking release. The `dqdoctor` command, the
`demo → check → rules-init → check → export` flow, and the zero-config
experience are preserved; the execution engine, rule contract, result model
and exit codes changed.

## TL;DR

```bash
pip install --upgrade "dq-doctor>=1.0"

# convert any 0.7 file once
dqdoctor migrate --in rules.yml --out contract.yml
# or, from a .dqdoctor.yml
dqdoctor migrate --in .dqdoctor.yml --out contract.yml

dqdoctor check --db data.duckdb --all-tables --rules contract.yml --ci
```

## What changed

### 1. Rules are a pinned contract, not learned per run

0.7 generated rules from the batch under test, then validated those same
rules against that same data. A `range` rule built from observed min/max
always passed; a dirty value became "accepted".

1.0 splits the two modes:

| Command | Mode | What you get |
|---|---|---|
| `dqdoctor check` (no `--rules`) | explore | every induced bound is a **SUGGESTION**, nothing counts as verified, score is `n/a` |
| `dqdoctor rules-init` | generate | an editable `contract.yml` from a reference batch |
| `dqdoctor check --rules c.yml` | contract | the pinned rules executed as written; nothing is re-learned |

A contract freezes enums, ranges and severities. Checking a new batch
cannot silently widen its own accepted set.

### 2. Rule ids are stable and table-scoped

| 0.7 | 1.0 |
|---|---|
| `not_null.user_id.3` (global counter, changes every run) | `orders/not_null:user_id` |
| one rule per `(type, column)`; a second was silently dropped | multiple rules per column, distinguished by id |

The migration strips the old counter suffix and prefixes the table name.

### 3. Statuses are explicit

| Status | Meaning |
|---|---|
| `pass` | the rule executed and the data satisfied it |
| `fail` | the rule executed and the data violated it |
| `skip` | the rule could not run (missing params, wrong dtype, disabled) |
| `suggestion` | a bound learned from this batch (explore mode only) |
| `error` | execution/config failure (affects the exit code, never scored) |

Consequences vs 0.7:

- an empty table with an executed `not_null` is a **PASS**, not "no data";
- a custom SQL rule returning `0` is a **PASS** (0.7 treated `0` rows as
  "suggestion" because it inferred status from counters);
- `unique` only compares **non-null** values - NULL-ness is `not_null`'s job
  (0.7 counted NULLs as duplicates and failed nullable unique columns);
- `freshness` only runs on real TIMESTAMP/DATE columns. A `*_time*` INTEGER
  or VARCHAR column used to crash the whole check (0.7 raised
  `TypeError: datetime - int`); it is now a SKIP.

### 4. Quality score

| 0.7 | 1.0 |
|---|---|
| `100` when nothing ran | `n/a` (null) when nothing executed |
| flat pass rate | severity-weighted: high 1.0, medium 0.5, low 0.25 |
| PII and FK knock the score down | PII is an independent finding; FK affects the gate, not the score |

`score_version: "1.0"` is written next to every score so historical reports
stay interpretable.

### 5. CLI flags

| 0.7 | 1.0 |
|---|---|
| `--db` only | `--db` accepts a path, a URL, or a `datasources:` alias |
| `--ci` + `--max-failures` | plus `--fail-on high|medium|low` |
| exit 0/1 | `0` ok/within policy, `1` gate tripped, `2` input/config/exec error |
| `--llm-key` on `check` | LLM suggestions are not part of the 1.0 check path (see limitations) |
| `--out report.html` only | `--out` (HTML) + `--json` + `--junit` |
| `--rules` = 0.7 rules file | `--rules` = 1.0 contract; 0.7 files get a migration hint |
| `--save-profile` | removed; run `profile --out` then `drift --old --new` |
| `serve --db` | `serve --report report.json` (reads an existing JSON report) |

### 6. Configuration

`.dqdoctor.yml` is now a datasource registry:

```yaml
datasources:
  prod: postgresql://user:pass@host:5432/db?schema=analytics
  local: demo.duckdb
  files: exports/2026-11/
default: local
```

`tables:` / `disable_rules:` / `severity:` / `sql_rules:` are **gone** from
the config. Those concepts live in the contract file, where they are
explicit, versioned and exportable. `dqdoctor migrate` converts them.

### 7. Datasources

New in 1.0:

- CSV / TSV / Parquet / JSON / JSONL files (or a directory of them) are
  registered as DuckDB views and go through the same rules and reports;
- `?schema=` selects a non-default PostgreSQL schema;
- `mysql://` is normalized to `mysql+pymysql://` (the old docs told you to
  use `mysql://`, which SQLAlchemy could not resolve);
- credential-bearing URLs are redacted in every report, log and error.

### 8. Safety

| 0.7 behaviour | 1.0 |
|---|---|
| `demo --output existing.duckdb` **deleted** the file | refuses without `--force`; writes a temp file and atomically replaces |
| `init` overwrote `.dqdoctor.yml` | refuses without `--force` |
| raw sample values in reports | text min/max fingerprinted, samples never serialized |
| `--verbose-rules` read the rules file 3 times | removed (the contract is the single source) |
| table names interpolated into dashboard HTML | autoescaped |

## Step-by-step

1. **Upgrade**
   ```bash
   pip install --upgrade "dq-doctor>=1.0"
   dqdoctor --version   # 1.0.x
   dqdoctor doctor      # optional extras report
   ```
2. **Migrate your rules**
   ```bash
   dqdoctor migrate --in rules.yml --out contract.yml
   dqdoctor migrate --in .dqdoctor.yml --out contract.yml
   ```
   Review the output: ids are now `table/type:column`, params keep numeric
   precision as strings, `sql_rules` become `type: sql` entries with an
   explicit `expect` block.
3. **Rebuild your config**
   ```bash
   dqdoctor init --force
   ```
   Add your datasources under `datasources:`. Credentials in a URL are
   redacted before being stored, so a contract never carries a password -
   pass the URL with `--db` or reference an alias.
4. **Pin against a known-good batch**
   ```bash
   dqdoctor rules-init --db prod_alias --all-tables --out contract.yml
   ```
   Edit severities and bounds; disable rules with `enabled: false`.
5. **Gate your pipeline**
   ```bash
   dqdoctor check --db prod_alias --all-tables --rules contract.yml \
     --out report.html --json report.json --junit junit.xml \
     --ci --max-failures 0 --fail-on high
   ```
6. **Onboard legacy failures**
   ```bash
   dqdoctor baseline capture --db prod_alias --rules contract.yml --out baseline.json
   dqdoctor check --db prod_alias --all-tables --rules contract.yml \
     --baseline baseline.json --ci
   ```
   Known failures are exempted; the same rule failing *more* (or a new FK
   orphan) still trips the gate.

## Exit codes

| Code | Meaning |
|---|---|
| `0` | all checks passed, or failures stayed within policy |
| `1` | quality gate tripped (failures above `--fail-on`, or count > `--max-failures`) |
| `2` | input/config/execution error (missing contract, bad datasource, SQL rule error) |

Execution errors are never exempted by a baseline.

## Export changes

| Format | 0.7 | 1.0 |
|---|---|---|
| dbt | `tests:` key (deprecated in dbt 1.8+) | `data_tests:`; ranges as `dbt_utils.expression_is_true` with numeric literals |
| GX | 0.x suite shape | GX 1.x `ExpectationSuite` (`type`/`kwargs`) |
| Soda | `invalid_count(x) = 0: { values: [...] }` | `invalid_count(x) = 0:` + `valid values:` |
| Deequ | bespoke JSON | pydeequ constraint mapping, consumer stated |
| markdown | data dictionary | full contract table, includes disabled rules |

Rule types with no equivalent in a target are listed explicitly in the
export (dbt comments, GX `meta.unmapped_rule_ids`, Soda comments, Deequ
`unmapped_rule_ids`) instead of disappearing.
