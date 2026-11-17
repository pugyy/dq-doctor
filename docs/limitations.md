# dq-doctor 1.0 limitations

Honest statement of what is verified, what is approximate, and what is not
covered, as of 1.0.0.

## Verified (executed locally)

- **DuckDB**: full coverage - profiling, all built-in rules, SQL rules,
  declared + heuristic FK, file sources (CSV/Parquet/JSON), sampling.
- **Rule semantics**: nullable `unique`, empty-table `not_null`, SQL rule
  returning 0, missing-parameter skips, suggestion-vs-pass separation -
  covered by `tests/test_regressions.py`.
- **Exit codes**: 0 / 1 / 2 plus the `--fail-on` x `--max-failures`
  interaction (`tests/test_engine.py`).
- **Baseline**: exemption, deterioration still gating, errors never
  exempted (`tests/test_engine.py`).
- **Reports**: text min/max redaction, no raw samples in JSON/HTML, HTML
  autoescape, credential redaction (`tests/test_integration.py`).
- **Performance**: 40-column profile = 2 queries; 1M rows x 4 columns =
  3 queries (`tests/test_perf.py`).

## Not verified in this environment

- **PostgreSQL / MySQL end-to-end**: `tests/test_backends.py` exists and
  runs in CI against real services, but this workstation had no Docker
  daemon, so it was **not executed locally**. Backend-specific paths
  (session read-only, `information_schema` queries, `<=>` vs
  `IS NOT DISTINCT FROM`, schema selection) are therefore unproven here.
  CI is the first real run.
- **dbt parse/test**: the exporter emits dbt >= 1.8 `data_tests` YAML with
  numeric literal ranges, but no dbt project parsed it. `dbt_utils` is
  required for range expressions.
- **GX 1.x loader**: suite JSON follows the 1.x shape
  (`version`/`type`/`name`/`expectations[].type/kwargs`), not yet fed
  through a real GX install.
- **SodaCL scan**: `valid values:` follows SodaCL docs; no Soda CLI run
  validated it.
- **MCP stdio client**: the server uses the official `mcp` SDK and reuses
  the engine, but no full client round-trip was executed here.
- **Python 3.14 / 3.15**: `requires-python` is `>=3.12`; CI runs 3.12,
  3.13, 3.14. 3.15 is claimed only once a CI run passes with the full
  dependency set (not yet).

## Known approximations

### Sampling

`--sample-rows` profiles a deterministic **first-N slice**
(`SELECT * FROM t LIMIT n`), not a random sample: portable across the three
backends, reproducible, and value-free in SQL text, but biased on sorted or
clustered tables. Sampling applies to **profiling only**; rule execution
always scans the full table, so a sampled pass can never gate a batch. The
profile records method, sample size and coverage.

### Heuristic foreign keys

Candidates are `*_id` name matches gated by type family (int/text) and
target uniqueness, marked `declared: false`, confidence 0.6. They
participate in the gate like declared keys; disable with
`CheckEngine(..., include_heuristic_fk=False)`.

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
Guardrails: read-only sessions, single-statement SELECT/WITH, statement
timeout, one-row/one-column contract. An operator can still write an
expensive read-only query; `--sql-timeout` is the mitigation.

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
