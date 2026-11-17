# dq-doctor 1.0 limitations

Honest statement of what is verified, what is approximate, and what is not
covered, as of 1.0.0.

## Verified (executed locally)

- **DuckDB**: profiling, all built-in rules, SQL rules, declared + heuristic
  FK, file sources (CSV/Parquet/JSON), sampling.
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
  redacted.
- **Identifiers**: CJK names, hyphens and digit-leading names work
  (quoted + escaped); control characters and double quotes are rejected.
- **Performance**: 40 integer columns = 2 queries; 1M rows x 4 columns =
  3 queries. Text columns cost one extra `DISTINCT ... LIMIT` each, because
  PII evidence needs sample values (`tests/test_perf.py`).
- **Coverage**: 80.9% line coverage, gated at 75% in `pyproject.toml`.

## Not verified in this environment

- **PostgreSQL / MySQL end-to-end**: `tests/test_backends.py` runs in CI
  against real services but was **not executed locally** (no Docker daemon
  on this machine). Backend-specific paths - session read-only,
  `information_schema` queries, `<=>` vs `IS NOT DISTINCT FROM`, schema
  selection - are therefore unproven here. The `DATABASE()`-on-PostgreSQL
  bug found by audit is fixed and pinned by a source-level test, but a live
  PostgreSQL run is still the first real proof.
- **CI has not run**: the workflow targets `main`; the `v1.0` branch has
  never been pushed, so no CI job has executed.
- **dbt parse/test**: exporter emits dbt >= 1.8 `data_tests` with numeric
  literal ranges; no dbt project parsed it. `dbt_utils` is required for
  range expressions.
- **GX 1.x loader**: suite JSON follows the 1.x shape; not fed through a
  real GX install.
- **SodaCL scan**: `valid values:` follows the documented syntax; no Soda
  CLI run validated it.
- **MCP stdio client**: server uses the official `mcp` SDK; no full client
  round-trip was executed (SDK not installed here).
- **Python 3.14 / 3.15**: `requires-python >= 3.12`; local run was 3.12 only.

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

The operator's query is the product input and is not parameterizable.
Guardrails:

- read-only sessions (PostgreSQL `default_transaction_read_only`, MySQL
  `SET SESSION TRANSACTION READ ONLY`, DuckDB opened read-only);
- shape policy (`sqlpolicy`): single statement, must start with
  `SELECT`/`WITH`, **no write keywords anywhere** (this blocks
  data-modifying CTEs such as `WITH d AS (DELETE ... RETURNING *) SELECT`),
  and **no file/network reader functions** (`read_text`, `read_csv_auto`,
  `read_parquet`, ...) which a read-only session does not stop;
- statement timeout, plus a one-row/one-column scalar contract.

An operator can still write an expensive read-only query; `--sql-timeout`
is the mitigation. The policy is a shape guard, not a full SQL parser.

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
