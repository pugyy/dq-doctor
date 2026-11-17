# Custom SQL rules (1.0)

A SQL rule is a query **you** write into your contract to check your own
data. It runs through a guarded primitive.

## Contract syntax

```yaml
version: 1
tables:
  orders:
    rules:
      - id: orders/sql:no_negative_amounts
        type: sql
        column: '*'
        params:
          query: SELECT COUNT(*) FROM orders WHERE total_amount < 0
          expect: {mode: eq, value: 0}
        severity: high
        reason: amounts must never be negative

      - id: orders/sql:row_volume
        type: sql
        column: '*'
        params:
          query: SELECT COUNT(*) FROM orders
          expect: {mode: between, min: 1000, max: 5000000}
        severity: medium
```

## `expect` contract

| Mode | Meaning | Fields |
|---|---|---|
| `eq` | scalar equals `value` | `value` |
| `lte` | scalar <= `max` (or `value`) | `max` |
| `gte` | scalar >= `min` (or `value`) | `min` |
| `between` | `min` <= scalar <= `max` | `min`, `max` |

Missing or malformed `expect` -> the rule is **SKIP**ped with a message
(1.0 never silently assumes `== 0`).

## Scalar result requirement

The query must return **exactly one row and one column**. Anything else is
an **ERROR** result:

- `SELECT id, qty FROM sales` -> "query returned 2 columns"
- `SELECT ... WHERE false` on an empty result -> "returned no rows"

## Guardrails

| Guard | Behaviour |
|---|---|
| read-only session | PostgreSQL `default_transaction_read_only`, MySQL `SET SESSION TRANSACTION READ ONLY`, DuckDB opened read-only |
| single statement | must start with `SELECT`/`WITH`; `;` mid-query rejected |
| timeout | `--sql-timeout` (default 30s); SQL backends use statement timeouts, DuckDB interrupts the connection |
| error visibility | failures are `error` results -> exit code `2`, never a silent pass |
| baseline | errors are **never** exempted |

```bash
dqdoctor check --db prod --all-tables --rules contract.yml --ci --sql-timeout 10
```

## Migration from 0.7

0.7 config:

```yaml
tables:
  orders:
    sql_rules:
      - name: order_amount_positive
        query: "SELECT COUNT(*) FROM orders WHERE total_amount <= 0"
        expect: 0
```

```bash
dqdoctor migrate --in .dqdoctor.yml --out contract.yml
```

becomes:

```yaml
- id: sql:order_amount_positive
  type: sql
  column: '*'
  params:
    query: SELECT COUNT(*) FROM orders WHERE total_amount <= 0
    expect: {mode: eq, value: 0}
```

## Writing good rules

- Return a single count or scalar; the comparison belongs in `expect`.
- Use the table's own name in the query (`orders`, not an alias of the
  datasource) - the query runs against the checked table's database.
- Keep queries bounded: they run once per check, against the full table.
- Prefer built-in rules (`row_count`, `cross_field`, `regex`) where they
  express the same thing - they get short-circuiting and typed messages.
