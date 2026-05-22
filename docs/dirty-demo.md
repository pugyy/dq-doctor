# Dirty Demo Walkthrough

The dirty demo generates a DuckDB database with intentional data quality issues so you can see dq-doctor in action.

## Generate

```bash
dqdoctor demo --dirty
```

Creates `dirty.duckdb` with two tables: `dirty_users` and `dirty_orders`.

## Issues Included

| Issue | Details |
|-------|---------|
| NULL values | 3 orders with `user_id = NULL`, 1 order with `status = NULL` |
| Negative amounts | `total_amount` values: -50.00, -10.00, -5.00, -200.00 |
| Orphan references | `user_id = 99` (not in `dirty_users`) |
| Invalid enums | `status = 'unknown_status'` |
| Stale timestamps | `created_at` up to 168 hours old |
| PII in plain text | emails and phone numbers in `dirty_users` |
| Invalid payment methods | `bitcoin` and `cash` outside accepted set |

## Commands to Try

```bash
# Full check
dqdoctor check --db dirty.duckdb --all-tables --out report.html

# Referential integrity
dqdoctor refint --db dirty.duckdb

# FK discovery
dqdoctor fk --db dirty.duckdb

# PII detection (visible in profile)
dqdoctor profile --db dirty.duckdb --table dirty_users

# Export to dbt
dqdoctor export --db dirty.duckdb --table dirty_orders --format dbt --out schema.yml

# Generate editable rules
dqdoctor rules-init --db dirty.duckdb --table dirty_orders --out rules.yml
```

## Clean Demo (All Pass)

```bash
dqdoctor demo
dqdoctor check --db examples/ecommerce/demo.duckdb --all-tables --out report.html
```
