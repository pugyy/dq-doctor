# Changelog

## v1.0.0

First stable release. Breaking changes; see
[Migration guide](docs/migration-1.0.md).

### Audit fixes (post-review pass)

An external review of the first 1.0 build found cases where tests passed but
behaviour was wrong. All are fixed and pinned by regression tests
(`tests/test_audit_*.py`):

- **Sampling could gate and mislead.** A sampled profile reported
  `non-null = full_rows` against `distinct = sample_size`, producing 950
  phantom duplicates on a 1000-row unique column, and under-reported NULLs
  by the sampling ratio. Now: `check --rules` always profiles the full
  table (`--sample-rows` is explore-mode only), every `ColumnProfile`
  records `stats_row_count` (its own denominator), and
  `SamplingInfo.random` is explicit.
- **PostgreSQL crashed on the default URL.** `queries.py` gated the MySQL
  `DATABASE()` call on "schema is unset" instead of on the backend, so a
  PostgreSQL URL without `?schema=` failed at the first metadata query.
- **Airflow operator never ran its body.** `__getattr__` cannot override
  `BaseOperator.execute` (the MRO wins before `__getattr__`). `execute` is
  now defined explicitly on the class.
- **Contracts stored a redacted datasource.** `rules-init` wrote
  `ds.describe()` (password `***`), so `check --rules` could not reconnect.
  New `persistent_ref()` returns the original spec for storage; `describe()`
  stays display-only.
- **FK orphans did not gate without a baseline.** The referential check was
  inside `if baseline is not None`. It now gates unconditionally; a baseline
  only exempts recorded pairs.
- **Execution errors exited 0 without `--ci`.** `decide_exit` is now called
  regardless of `--ci`; `--ci` only controls whether gate failures exit 1.
- **Printed failure count ignored `--fail-on`.** A run with only low
  failures printed "N non-exempt failure(s)" while exiting 0.
- **Redaction destroyed statistics.** `Decimal`/`date`/`datetime` min/max
  were fingerprinted, hiding amount and time ranges. Only `str`/`bytes` are
  fingerprinted now.
- **SQL policy was too weak and too eager.** Data-modifying CTEs
  (`WITH d AS (DELETE ... RETURNING *) SELECT`), `read_text`/`read_csv_auto`
  /`read_parquet` and multi-statement text all passed. Now rejected;
  keywords inside string literals and comments are no longer false
  positives.
- **Identifiers rejected real names.** CJK (`订单`), hyphenated and
  digit-leading identifiers failed validation. Now accepted and quoted with
  escaped quote characters.
- **Rule ids were not table-scoped outside `rules-init`.** Hand-written or
  migrated multi-table contracts were rejected as duplicate ids. Scoping now
  happens in `validate_spec`.
- **`init` wrote an unusable `default`.** `Registry.default` was never
  read, so `check --config` failed with "Empty datasource spec".
- **`demo` unlinked before writing.** It now renames the previous database to
  `.bak` instead of deleting it.
- **`accepted_values` stringified enum values**, breaking integer enums on
  PostgreSQL.
- **JUnit `skipped` count** omitted exempted/suggestion elements.
- **HTML report lost the column profile** (and rule source).
- **`llm/client.py` imported a deleted class** and embedded sample values in
  the prompt; rewritten to metadata-only suggestions.
- **Directory sources with duplicate stems** (`users.csv` + `users.parquet`)
  failed on duplicate view names.
- **Heuristic FK** ignored `parent_id -> parents.id` and treated empty
  target columns as keys.
- Coverage gate added (`--cov-fail-under=75`); suite is now 134 tests at
  ~81% coverage.

### New: contract-based checking

- `rules-init` generates a versioned, editable contract (YAML/JSON) where
  rule ids are stable and table-scoped (`orders/not_null:user_id`).
- `check --rules` executes the pinned contract; enums and bounds are never
  re-learned from the batch under test.
- Zero-config `check` is explore mode: induced bounds are `suggestion`s,
  nothing counts as verified, and the score is `n/a`.
- Multiple independent rules per column are kept.

### New: explicit statuses and honest scoring

- Statuses: `pass` / `fail` / `skip` / `suggestion` / `error`.
- Empty table with an executed rule is a PASS; a SQL rule returning 0 is a
  PASS; missing parameters are SKIPs; execution failures are ERRORs.
- Severity-weighted score (high 1.0, medium 0.5, low 0.25), `None` when no
  rule executed, `score_version` recorded.
- PII is an independent finding with evidence and no raw values.

### New: CI contract

- `--ci`, `--max-failures`, `--fail-on high|medium|low` with documented
  combination semantics: `--fail-on` selects participating failures,
  `--max-failures` tolerates a count of them.
- Exit codes: `0` ok, `1` gate, `2` input/config/execution error.
- Multi-table runs aggregate before applying thresholds; each relationship
  is counted once per run.
- `--json` (versioned, redacted) and `--junit` outputs alongside HTML.
- Known-failure baselines: `baseline capture`, `--baseline`; known failures
  are exempted, deterioration and new failures still gate, errors are never
  exempted.

### New: rule types

`regex`, `row_count`, `cross_field`, plus `sql` with an explicit
`eq/lte/gte/between` scalar contract. SQL rules run read-only with
statement timeouts and single-statement guards.

### New: datasources

- CSV / TSV / Parquet / JSON / JSONL files and directories, via DuckDB.
- PostgreSQL `?schema=` selection; `mysql://` normalized to PyMySQL.
- Named datasource aliases in `.dqdoctor.yml`.
- Credentials redacted everywhere; explicit CLI values beat config;
  missing/invalid config files produce clear diagnostics.

### New: performance

- Profiling is batched: one aggregate per table (40 columns = 2 queries,
  1M rows = 3 queries; 0.7 used 4-5 queries per column).
- FK metadata and referential checks build one plan per run.
- Explicit, reproducible sampled profiling (method/size/coverage recorded;
  gating always full-scan).

### New: MCP server

`dqdoctor mcp` exposes `list_datasets`, `profile_table`, `run_check`,
`get_summary` over stdio, reusing the engine (stdout reserved for the
protocol).

### Fixed (reproduced before fixing)

- `unique` counted NULLs as duplicates and failed nullable unique columns.
- `freshness` on TIME/INTEGER columns crashed the whole check
  (`datetime - int`); freshness now requires a TIMESTAMP/DATE dtype.
- PII: TIME strings matched an IPv6 regex; `1.2.3.4` version strings
  matched IPv4; the `tel` name hint hijacked `hotel_id`; IPs were not
  validated.
- Empty tables reported executed rules as suggestions; scores were `100`
  with nothing checked.
- Multiple rules on one column were silently deduplicated.
- `demo --output` deleted existing files; `demo`/`init` overwrote without
  confirmation and could leave partial files.
- LLM failures were swallowed silently.
- MySQL connection strings in docs did not work with the installed driver.
- `--verbose-rules` re-read the rules file multiple times.
- Text min/max, distinct values and orphan samples leaked into reports.
- Dashboard interpolated table names into HTML unescaped.

### Changed

- `requires-python >= 3.12`; CI on Linux + Windows, Python 3.12-3.14.
- Version comes from package metadata; `dqdoctor --version`.
- dbt export uses `data_tests`; GX uses the 1.x suite shape; SodaCL uses
  `valid values`; Deequ states its consumer (pydeequ).
- Tests: fixed clock, no wall-clock dependence; 61 tests.

### Removed

- `correlate`, `lineage`, `fk` commands (superseded by the FK plan).
- `--llm-key` on `check`, `--verbose-rules`, `--save-profile`.
- 0.7 modules replaced by the engine (`connectors/`, `profiler`,
  `validator`, `rule_engine`, `reporter`, `custom_rules`, `sql_rules`,
  `pii_detector`, `fk_discovery`, `ref_integrity`, `correlation`,
  `lineage`, `config`).

## v0.7.1

- Fix: `--ci` counts referential integrity failures.
- Fix: quality score display.
- Fix: `--verbose-rules` shows config overrides.

## v0.7.0

- Quality score (0-100) per table.
- PII detection and referential integrity in the HTML report.
- `--verbose-rules`.

## v0.6.x

- Custom rules override auto rules; `rules-init`; `doctor` command;
  `--save-profile`; docs split; bilingual README.

## v0.5.0

- Usability release: docs, examples, `doctor`, `rules-init`.

## v0.4.0

- `.dqdoctor.yml`, custom SQL rules, referential integrity, dirty demo.

## v0.3.0

- PII detection, FK discovery, correlation, lineage, drift, Soda/Deequ
  export, dashboard, Airflow operator.

## v0.2.0

- Unified connection wrapper, dbt format, LLM-enhanced rules.

## v0.1.0

- Initial release: 5 heuristic rules, HTML reports, dbt/GX/Markdown export.
