# Export Formats

Export auto-generated rules for integration with other tools.

## dbt schema.yml

```bash
dqdoctor export --db demo.duckdb --table orders --format dbt --out schema.yml
```

Generates a dbt-compatible `schema.yml` with:
- `not_null` and `unique` as native dbt test types
- `accepted_values` as dbt native test
- `range` via `dbt_utils.expression_is_true` (requires dbt-utils package)

## Great Expectations

```bash
dqdoctor export --db demo.duckdb --table orders --format gx --out suite.json
```

Generates an Expectation Suite JSON.

## Soda CL

```bash
dqdoctor export --db demo.duckdb --table orders --format soda --out checks.yml
```

Generates Soda CL checks using `missing_count`, `duplicate_count`, `invalid_count` metrics.

## Deequ

```bash
dqdoctor export --db demo.duckdb --table orders --format deequ --out checks.json
```

Generates Deequ-style constraint JSON.

## Markdown Data Dictionary

```bash
dqdoctor export --db demo.duckdb --table orders --format markdown --out dict.md
```

Generates a human-readable data dictionary with column types, stats, and quality notes.
