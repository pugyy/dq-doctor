# dq-doctor 1.0 limitations

Honest statement of what is verified, what is approximate, and what is not
covered, as of 1.0.0.

## Verified (executed locally)

- **DuckDB**: profiling, all built-in rules, SQL rules, declared + heuristic
  FK, file sources (CSV/Parquet/JSON), sampling.
- **MySQL 9.5 and PostgreSQL 16.2 (live servers)**: `tests/test_backends.py`
  and `tests/test_live_backends.py` ran against real instances. Verified:
  identical verdicts from `unique`/`accepted_values`/`range`; read-only
  sessions rejecting writes; SQL rule scalar contracts; declared FK
  direction (including the MySQL default-database case); reserved-word
  table/column names (``order``, ``select``); `open(read_only=False)`
  actually writable on PostgreSQL.
- **Rule semantics**: nullable `unique`, empty-table `not_null`, SQL rule
  returning 0, missing-parameter skips, suggestion-vs-pass separation.
- **Sampling isolation**: `check --rules` always profiles the full table;
  `--sample-rows` only affects explore mode. `ColumnProfile.stats_row_count`
  records the counter's own denominator so a sampled count can never be
  compared with a full-table row count (`tests/test_audit_sampling.py`).
- **Exit codes**: 0/1/2, `--fail-on` x `--max-failures`, and execution
  errors exiting 2 **without** `--ci` (`tests/test_audit_gate.py`).
- **FK gating**: orphans gate with or without a baseline; a baseline only
  exempts specific known pairs.
- **Baseline**: exemption, deterioration still gating, errors never exempted.
- **Reports**: numeric/temporal statistics stay readable, text min/max is
  fingerprinted, no raw samples in JSON/HTML, HTML autoescape, credentials
  redacted (userinfo **and** query parameters).
- **Identifiers**: CJK names, hyphens and digit-leading names work
  (quoted + escaped); control characters and double quotes are rejected.
- **Windows console**: GBK output verified via subprocess test.
- **Performance**: 40 integer columns = 2 queries; 1M rows x 4 columns =
  3 queries. Text columns cost one extra `DISTINCT ... LIMIT` each, because
  PII evidence needs sample values (`tests/test_perf.py`).
- **Coverage**: ~84% line coverage, gated at 75% in `pyproject.toml`.

## Not verified in this environment

- **CI has not run**: the workflow targets all branches now, but the `v1.0`
  branch has never been pushed.
- **Live servers used for verification were local**: MySQL 9.5.0 and
  embedded PostgreSQL 16.2 (pgserver) on loopback. Non-default MySQL
  schemas via `?schema=` are exercised only in a skipped case because the
  local instance has a single database.
- **dbt parse/test**: exporter emits dbt >= 1.8 `data_tests` with numeric
  literal ranges; no dbt project parsed it. `dbt_utils` is required for
  range expressions.
- **GX 1.x loader**: suite JSON follows the 1.x shape; not fed through a
  real GX install.
- **SodaCL scan**: `valid values:` follows the documented syntax; no Soda
  CLI run validated it.
- **MCP stdio client**: server uses the official `mcp` SDK; no full client
  round-trip was executed (SDK not installed here).
- **Python 3.14 / 3.15**: local run was 3.12 only.

## Known approximations

### Sampling

`--sample-rows` profiles a deterministic **first-N slice**
(`SELECT * FROM t LIMIT n`), not a random sample: portable across the three
backends, reproducible, and value-free in SQL text, but biased on sorted or
clustered tables. `SamplingInfo.random` is always `false` so consumers never
assume otherwise.

**Sampling never gates.** In contract mode (`check --rules`) the engine
ignores `--sample-rows` entirely and profiles the full table; sampling is
available only in explore mode, where nothing is verified. Additionally,
every `ColumnProfile` records `stats_row_count` - the denominator its
null/distinct counters were computed over - so a rule can never compare a
sampled counter against a full-table row count.

### Heuristic foreign keys

A `*_id` column is a candidate for a table whose name matches the column
stem (`parent_id` -> `parents`, `user_id` -> `users`), or for a table with a
column of the same name. Candidates are additionally gated by type family
(int/text) and target-key uniqueness - an empty or all-NULL target column is
**not** a key. They are marked `declared: false`, confidence 0.6, and
participate in the gate like declared keys; disable with
`CheckEngine(..., include_heuristic_fk=False)`.

A column whose stem does not name its parent table (e.g. `parent_id` pointing
at a table called `p`) is deliberately **not** guessed.

### Timezone policy

Naive timestamps are interpreted as **local wall-clock time** (the
convention of most ETL-written `TIMESTAMP` columns); offset-bearing values
are compared in the process timezone. A value more than a second in the
future fails freshness explicitly.

### PII detection

Regex + column-name priors at a 50% match threshold over at most 10
sampled values. It is a **triage aid**, not a compliance tool: short
columns, obfuscated formats and non-CN formats are not covered. Findings
are informational and do not affect the score.

### SQL rules

The operator's query is the product input and is not parameterizable. Two
layers guard it:

**Layer 1 - connection restriction (authoritative on DuckDB files).**
DuckDB databases are opened with ``enable_external_access=false``. That is
an engine-level block, not a keyword list: ``query_table``, ``glob``,
replacement scans (``FROM 'file.parquet'``) and every ``read_*`` function
fail with ``PermissionException``. It also blocks extension loading.

**Layer 2 - shape policy (``sqlpolicy``).** Applied to every backend:

- single statement, must start with ``SELECT``/``VALUES``/``WITH``;
- no write keywords anywhere (blocks data-modifying CTEs such as
  ``WITH d AS (DELETE ... RETURNING *) SELECT``);
- no file/network reader functions - covers DuckDB ``read_*``/``glob``/
  ``query_table`` **and** PostgreSQL ``pg_read_file``/``pg_ls_dir`` **and**
  MySQL ``LOAD_FILE``;
- no ``FROM 'literal'`` replacement scans;
- string literals are removed *before* comments, so ``SELECT '--' ; DELETE``
  cannot hide a second command.

**Exception: file datasources (CSV/Parquet/JSON).** DuckDB views over files
re-read the file on each query, so ``enable_external_access`` cannot be
disabled there - it would block the datasource's own tables. A keyword
policy cannot enumerate every read shape (``JOIN 'x.parquet'``, comma
joins, ``parquet_metadata(...)``), so **SQL rules are refused outright on
file datasources**: ``check_sql`` returns a SKIP explaining that regex /
row_count / cross_field / range / accepted_values should be used instead.
If you need SQL rules over files, materialize the file into a DuckDB
database first (``dqdoctor`` then sees it as a normal table).

**Residual risk.** SQL sessions are also read-only (PostgreSQL
``default_transaction_read_only``, MySQL ``SET SESSION TRANSACTION READ
ONLY``, DuckDB file read-only). MySQL's statement only covers the *next*
transaction, so a driver that has already begun a transaction keeps write
capability within it - the shape policy is the guard on that path. An
operator can still write an expensive read-only query; ``--sql-timeout`` is
the mitigation. The policy is a shape guard, not a full SQL parser; an AST
whitelist (e.g. sqlglot) is the next step if untrusted rule authors are in
scope.

### Credentials

Datasources embedding credentials are **never persisted**: a contract
stores the redacted form. Both forms are masked - userinfo
(`postgresql://u:***@host/db`) and query parameters
(`?password=***`), while non-secret parameters such as `sslmode=require`
are kept so the reference stays descriptive. Pass the real URL with
`--db`, or register an alias in `.dqdoctor.yml` and use the alias.

Local paths are stored **absolute**, so a contract keeps resolving after
being moved or read from another directory; relative paths inside a
hand-written contract resolve against the contract's own directory.

`.gitignore` covers `contract.yml`, `*.contract.yml` and `*.duckdb.bak`
(the backup `demo --force` leaves behind).

### Console encoding

The CLI renders plain ASCII (`Console(emoji=False)`). Rich would otherwise
turn a rule id such as `not_null:a` into an emoji glyph, which a GBK
console cannot encode - the check would pass and the process would still
exit 1 on `UnicodeEncodeError`. Verified with a GBK subprocess test
(`tests/test_console_and_paths.py`).

### Score

Severity weights (1.0 / 0.5 / 0.25) and the linear pass-rate model are a
policy choice, not a measurement. `skip`/`suggestion`/`error` rules do not
enter the denominator; a table with no executed rules has no score.

## Deliberately removed in 1.0

- `correlate`, `lineage`, `fk` commands: heuristic-only correlation/lineage
  are superseded by the FK plan; declared FK metadata is far more reliable.
- `--llm-key` on `check`: LLM rule generation produced unvalidated
  suggestions mixed into the check path. The contract is now the only
  source of executed rules.
- `--verbose-rules`: the contract file **is** the verbose view.
- Top-level `rules:` in `.dqdoctor.yml`: replaced by the contract.
