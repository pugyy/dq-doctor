# Architecture (1.0)

## Module map

| Module | Responsibility |
|---|---|
| `datasources.py` | spec parsing (URL/path/alias), connection lifecycle, identifier quoting, schema selection, read-only sessions, timeouts, credential redaction |
| `queries.py` | metadata lookups (tables, columns) with bound parameters |
| `fileviews.py` | registers CSV/Parquet/JSON files as DuckDB views (the one place a path becomes SQL text, isolated and escaped) |
| `profiling.py` | table profiling orchestration (semantics, sampling info, PII evidence) |
| `aggregates.py` / `scanref.py` / `samples.py` | batched aggregate SQL, scan references, sample fetches |
| `rules.py` | rule types, parameter validation, numeric precision, freshness clock math |
| `rulecheck.py` | built-in rule execution (reuses profile aggregates, short-circuits) |
| `sqlrules.py` / `sqlpolicy.py` / `sqlexec.py` | guarded operator SQL rules: shape policy, scalar contract, execution primitive |
| `fkdeclared.py` / `fkcheck.py` | declared FK metadata, heuristic candidates, orphan checks |
| `contract.py` | contract load/save, validation, legacy migration |
| `suggest.py` | explore-mode suggestions (never executed) |
| `scoring.py` | severity-weighted score with breakdown |
| `engine.py` | one run: connection, FK plan, per-table profile+rules+score, baseline, exit decision |
| `gate.py` | scheduler-facing `run_gate` + Airflow operator |
| `outputs.py` | JSON / JUnit / HTML writers (redacted) |
| `redact.py` | value fingerprinting and payload redaction |
| `pii.py` | PII detection with evidence |
| `exporters/*` | dbt / GX / Soda / Deequ / markdown |
| `mcp_server.py` | stdio MCP tools over the engine |
| `dashboard.py` | read-only web view over a JSON report |
| `cli.py` | parameter handling and rendering only |
| `demo.py` | demo database creation (atomic replace) |

## One run

```
resolve(datasource) ──> open connection (read-only)
        │
        ├─ FK plan (declared + heuristic candidates) ──> check each once
        │
        └─ for each table:
             profile_table()            # 1 aggregate + a few extras
                │
                ├─ contract mode: execute_rules() + sql rules
                └─ explore mode:  suggest_for_table() -> SUGGESTIONs
                │
                └─ score_table() -> severity-weighted score / None

apply_baseline()  -> exempt known failures (deterioration still gates)
decide_exit()     -> 0 / 1 / 2    (single decision point)
```

The CLI, the Airflow operator, exporters and the MCP server all call
`CheckEngine.run` (or `gate.run_gate`), so a rule means the same thing
everywhere.

## Rule semantics

- The **profile** is computed once per table and reused: `not_null`,
  `unique`, `freshness`, `row_count` need no extra query; `range` and
  `accepted_values` short-circuit when the profiled bounds prove the answer.
- Values never enter SQL text. Statements combine literals,
  allowlist-quoted identifiers and bound parameters.
- Sampling affects profiling only; rules always scan the full table.

## Status model

| Status | Counted in score | Gates CI |
|---|---|---|
| `pass` | yes | no |
| `fail` | yes | yes (subject to `--fail-on` / `--max-failures` / baseline) |
| `skip` | no | no |
| `suggestion` | no | no |
| `error` | no | yes (exit `2`) |

## Extension points

- New rule type: add a checker in `rulecheck.py` (register in `_DISPATCH`)
  and a validator in `rules.py`.
- New export target: add `exporters/<name>.py` with `save(contract, path)`.
- New scheduler: call `dqdoctor.gate.run_gate`.
- New datasource backend: extend `datasources.parse_spec` and `Connection`
  (placeholder token + backend name).
