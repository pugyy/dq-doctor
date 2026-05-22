# Architecture

## Data Flow

```
dqdoctor check --db X --table T
  → profiler.profile_table(db, table) → ProfileResult
  → rule_engine.generate_rules(profile) → list[RuleSuggestion]
  → validator.validate_rules(db, table, rules) → list[ValidationResult]
  → reporter.build_report(profile, rules, results) → ReportResult
  → reporter.save_html(report, path) → HTML file
```

## Project Structure

```
dqdoctor/
  cli.py            Typer CLI (15 commands)
  models.py         Pydantic models
  profiler.py       Column profiling + semantic inference + PII detection
  rule_engine.py    5 heuristic rules + LLM integration
  validator.py      Rule execution via ConnectionWrapper
  reporter.py       HTML report via Jinja2
  config.py         .dqdoctor.yml loader
  demo.py           Demo database generation
  custom_rules.py   Load/merge custom rules (JSON/YAML)
  sql_rules.py      Execute custom SQL validation rules
  drift.py          Profile save/load/drift comparison
  pii_detector.py   PII regex detection
  fk_discovery.py   Cross-table FK discovery
  correlation.py    Column correlation (Pearson)
  lineage.py        Data lineage (FK + correlation)
  ref_integrity.py  Referential integrity checker
  dashboard.py      Flask web dashboard
  connectors/
    auto.py         ConnectionWrapper (DuckDB/PG/MySQL)
  exporters/
    dbt.py, gx.py, markdown.py, soda.py, deequ.py
  llm/
    client.py       OpenAI-compatible LLM client
  providers/
    airflow.py      Airflow operator
  templates/
    report.html     Jinja2 HTML template
  data/
    seed.sql        Clean demo data
    dirty_seed.sql  Dirty demo data (intentional issues)
```

## Supported Rules

| Rule | Trigger | Example |
|------|---------|---------|
| `not_null` | Zero nulls or identifier field | `order_id` has no nulls |
| `unique` | Identifier with ≥98% distinct rate | `user_id` is nearly unique |
| `accepted_values` | Category field with ≤20 distinct values | `status` has 4 values |
| `range` | Numeric column | `total_amount` in [45.00, 680.00] |
| `freshness` | Timestamp field | `created_at` within 24h |

## Semantic Type Inference

Column name pattern matching:
- `*id*` → identifier
- `*price*`, `*amount*`, `*cost*` → measure
- `*status*`, `*type*`, `*category*` → category
- `*time*`, `*date*`, `*at` → timestamp
- Unmatched → unknown
