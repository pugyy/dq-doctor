# Dirty Demo — dq-doctor 3-Minute Quickstart

This example shows how dq-doctor catches real data quality issues.

## Run It

```bash
# Install
pip install dq-doctor

# Generate dirty demo database (intentional issues)
dqdoctor demo --dirty

# Run full check — see what's broken
dqdoctor check --db dirty.duckdb --all-tables --out report.html

# Check referential integrity (orphan detection)
dqdoctor refint --db dirty.duckdb

# Open the report
# macOS: open report.html
# Windows: start report.html
# Linux: xdg-open report.html
```

## What You'll See

The dirty demo contains **intentional data quality issues**:

| Issue Type | Example |
|------------|---------|
| NULL values | `user_id` is NULL in orders |
| Negative amounts | `total_amount = -50.00` |
| Orphan references | `user_id = 99` (doesn't exist) |
| Invalid enum values | `status = 'unknown_status'` |
| Outdated timestamps | `created_at` is 7 days old |
| PII exposure | emails, phone numbers in plain text |

## Expected Output

```
dirty_orders: Rules 14  Passed 7  Failed 7
  PASS not_null on order_id: ...
  FAIL not_null on user_id: 3 null rows found
  FAIL unique on order_id: ...
  FAIL range on total_amount: 4 values outside [0.00, 99999.99]
  FAIL accepted_values on status: 2 values not in accepted set
  ...
```

## Next Steps

```bash
# Export rules to dbt schema.yml
dqdoctor export --db dirty.duckdb --table dirty_orders --format dbt --out schema.yml

# Generate editable rules file
dqdoctor rules-init --db dirty.duckdb --table dirty_orders --out rules.yml
```
