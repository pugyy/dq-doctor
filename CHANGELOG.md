# Changelog

## v1.0.5

Fifth audit pass. The 1.0.4 fixes held; two real bugs were hiding behind a
skip and a version-range gap.

### Fixed

- **MySQL `?schema=` appended to the database instead of replacing it**
  (`mysql://h/dqtest?schema=other` connected to database `dqtest/other`,
  which MySQL rejects). `?schema=` now replaces the database segment; the
  fix is verified against a real second database (`dqtest2`), covering
  table listing and declared-FK discovery on the selected database. The
  `mysql_schema` bound-parameter branches that this made unreachable are
  removed (`queries.py`, `fkdeclared.py`, `Connection`): MySQL always
  filters by `DATABASE()`.
- **`postgresql://` now normalizes to `postgresql+psycopg://`.** A bare URL
  resolves to psycopg3 on SQLAlchemy 2.1 but psycopg2 on 2.0, so
  `[sql]`-only installs broke on one version or the other. The explicit
  driver works on both; verified from clean venvs with SQLAlchemy 2.0.36
  and 2.1.9 against live PostgreSQL 16 and MySQL 9.
- `dqdoctor doctor` checks `psycopg` (the driver `[sql]` ships) instead of
  `psycopg2`; `docs/postgres-mysql.md` updated to match.

### CI

`tests/test_live_backends.py` joined the integration job with
`DQ_LIVE_REQUIRED=1` and `DQTEST_MYSQL_ADMIN`, so unreachable services fail
instead of skipping and the second-database case has what it needs.

## v1.0.4

Fourth audit pass: four regressions found in 1.0.3, all reproduced then fixed.

### Fixed

- **The replacement-scan check rejected everyday SQL.** The `,` branch added
  for `FROM t, 'file'` fired on every function-call argument:
  `IN ('ok','bad')`, `COALESCE(a,'x')`, `replace(name,'a','b')` were all
  refused despite being core cleaning-rule syntax. The branch is removed;
  the comma table form is stopped at the engine level instead (verified:
  `PermissionException` on DuckDB), and PG/MySQL reject it as a syntax
  error.
- **A single-file datasource was persisted as its parent directory**, so
  `rules-init --db orders.parquet` wrote a contract that reloaded as the
  whole directory (extra files as tables). A single file now stays a single
  file; only multi-file sources in one directory are stored as the
  directory.
- **`pip install dq-doctor[sql]` could not connect to PostgreSQL.** The
  extra shipped psycopg2 while SQLAlchemy 2.1 resolves a bare
  `postgresql://` URL to the psycopg3 driver. The extra now installs
  `psycopg[binary]>=3.1`; verified from a clean `[sql]`-only venv against
  live PostgreSQL 16 and MySQL 9.
- **Live-server tests swallowed real failures as skips.** The reachability
  probe caught bare `Exception`, so a driver bug surfaced as "not
  reachable" (and made the suite flaky between runs). It now catches only
  `OperationalError`/`DatasourceError`, and setting `DQ_LIVE_REQUIRED=1`
  turns unreachable servers into failures for CI.

### Tests

197 tests (was 190), 84.1% coverage. New cases: `IN`/`COALESCE`/`replace`
policy acceptance, comma-form engine-level block, single-file persistence.

## v1.0.3

Live-backend verification (MySQL 9.5.0, PostgreSQL 16.2). Running the
cross-backend suite against real servers exposed two bugs that DuckDB-only
testing could not see.

### Fixed

- **MySQL declared foreign keys were never discovered when the URL uses the
  default database.** `_declared_sqla` bound `None` into
  `table_schema = :schema` (the default-database case sets
  `mysql_schema = None`), which matches no rows. The query now uses
  `DATABASE()` when no schema is given, mirroring the existing metadata
  fix. FK direction and orphan detection on MySQL now work.
- **`DataSource.open(read_only=False)` was still read-only on PostgreSQL.**
  `default_transaction_read_only=on` was hardcoded in `connect_args`, so
  fixtures and maintenance tooling could not even `DROP TABLE IF EXISTS`.
  The flag now follows the `read_only` argument; `check` still enforces
  read-only itself, and MySQL gets the same treatment.

### Verified against live servers

`tests/test_backends.py` (8 cases) and `tests/test_live_backends.py`
(6 cases) run against a local MySQL 9.5.0 and PostgreSQL 16.2: identical
verdicts per backend, read-only sessions rejecting writes, SQL rule scalar
contracts, declared FK direction, reserved-word identifiers
(`order`, `select`), and engine-level read-only enforcement with a row
that must survive.

190 tests, 84% coverage.

## v1.0.2

Third audit pass. Closes the remaining release blockers.

### Security

- **File datasources can no longer run SQL rules.** The engine-level
  `enable_external_access` block cannot apply to CSV/Parquet/JSON views
  (they re-read the file per query), and the keyword policy provably missed
  `JOIN 'x.parquet'`, comma joins, `parquet_metadata(...)` and
  `"read_text"(...)`. SQL rules on file datasources now return a SKIP with
  a remediation message instead of executing. The policy also gained
  JOIN/comma replacement-scan detection and the `parquet_*` readers.
- **Query-parameter secrets are redacted.** `?password=`, `?passwd=`,
  `?token=` and friends are masked in `describe()` and in
  `safe_persistent_ref()`; `?sslmode=require` is kept and no longer
  triggers a false "embeds credentials" warning.
- `persistent_ref()` (raw URL) removed so it cannot be called by mistake.

### Fixed

- **Windows GBK console no longer turns a passing check into exit 1.**
  Rich rendered rule ids like `not_null:a` with an emoji glyph that GBK
  cannot encode; the console is now ASCII-only (`emoji=False`). Pinned by a
  GBK subprocess test.
- **Contract paths resolve against the contract's directory**, and
  `rules-init` stores local paths absolute, so a contract keeps working when
  read from another cwd.
- **`REPLACE()` is no longer rejected as a write keyword** (only
  `REPLACE INTO` is); `json_each`/`json_tree` are no longer treated as file
  readers.

### Tests

177 tests (was 165), 81.1% coverage. New: `tests/test_console_and_paths.py`
(GBK subprocess, contract-relative paths), plus JOIN/comma/`parquet_metadata`
bypass cases.

## v1.0.1

Second audit pass. Fixes two release blockers introduced by the first fix
round, plus scheduling/CI gaps.

### Security

- **SQL rules could escape the database.** The keyword/function blacklist
  missed `query_table`, `glob`, DuckDB replacement scans (`FROM 'x.parquet'`),
  `pg_read_file`, `pg_ls_dir` and `LOAD_FILE`, and `SELECT '--' ; DELETE`
  slipped past the multi-statement check because comments were stripped
  before string literals. Now:
  - DuckDB datasources open with `enable_external_access=false`, so file
    and network reads fail at the engine level regardless of the statement
    text;
  - the shape policy gained the missing functions, a replacement-scan
    check, and correct strip order (literals before comments);
  - file datasources are documented as an exception (their views re-read
    the file per query, so the engine block cannot apply there).
- **Contracts no longer persist credentials.** `rules-init` writes the
  redacted datasource for URL sources and prints a warning; `check` refuses
  a contract whose datasource still contains `***`. `.gitignore` now covers
  `contract.yml`, `*.contract.yml` and `*.duckdb.bak`.

### Fixed

- `run_gate` / `DQDoctorOperator` accept `baseline_path`, so schedulers can
  onboard legacy orphan data the same way the CLI does.
- `rules-init` no longer prints a redacted URL as the "next command".
- Version bumped to 1.0.1 so this build is distinguishable from the first
  1.0.0 artifact.
- CI triggers on any branch (`branches: ["**"]`), so `test_backends.py` can
  actually run against real PostgreSQL/MySQL.

### Tests

164 tests (was 134), 80.9% coverage. New: `tests/test_audit_sql_bypass.py`
(19 bypass shapes + engine-level restriction), `tests/test_secret_handling.py`.

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
