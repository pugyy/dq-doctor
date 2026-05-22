# Configuration File

Use `.dqdoctor.yml` to persist settings instead of passing flags every time.

## Create Config

```bash
dqdoctor init
```

This creates a `.dqdoctor.yml` in the current directory:

```yaml
db: examples/ecommerce/demo.duckdb

tables:
  orders:
    freshness:
      created_at:
        max_age_hours: 48
    disable_rules:
      - range:user_id
    severity:
      order_id:not_null: high
    sql_rules:
      - name: order_amount_positive
        query: "SELECT COUNT(*) FROM orders WHERE total_amount <= 0"
        expect: 0
```

## Use Config

```bash
dqdoctor check --config .dqdoctor.yml --table orders
```

If `.dqdoctor.yml` exists in the current directory, it's loaded automatically (no `--config` needed).

## Config Reference

| Field | Type | Description |
|-------|------|-------------|
| `db` | string | Default database path or connection string |
| `tables.<name>.freshness.<col>.max_age_hours` | int | Override freshness threshold |
| `tables.<name>.disable_rules` | list | Rules to skip (`rule_type:column` or `rule_type`) |
| `tables.<name>.severity` | dict | Override severity (`column:rule_type: level`) |
| `tables.<name>.sql_rules` | list | Custom SQL rules (see [custom-sql-rules.md](custom-sql-rules.md)) |

## Disable Rules

```yaml
tables:
  orders:
    disable_rules:
      - "range:user_id"        # disable range check on user_id
      - "freshness"            # disable all freshness checks
```

## Override Severity

```yaml
tables:
  orders:
    severity:
      "order_id:not_null": high
      "total_amount:range": critical
```
