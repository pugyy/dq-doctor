# Export formats (1.0)

Every exporter reads the **contract** (not a live profile), so what you
export is exactly what you gate on: overrides, disabled rules and effective
parameters included.

```bash
dqdoctor export --rules contract.yml --format dbt      --out schema.yml
dqdoctor export --rules contract.yml --format gx       --out suite.json
dqdoctor export --rules contract.yml --format soda     --out checks.yml
dqdoctor export --rules contract.yml --format deequ    --out deequ.json
dqdoctor export --rules contract.yml --format markdown --out dict.md
```

| Exporter | Target | Version |
|---|---|---|
| `dbt` | dbt schema YAML | dbt >= 1.8 (`data_tests`) |
| `gx` | Great Expectations suite JSON | GX 1.x suite shape |
| `soda` | SodaCL checks | SodaCL `valid values` syntax |
| `deequ` | pydeequ constraint mapping | consumer: pydeequ scripts |
| `markdown` | contract table | - |

## dbt

```yaml
version: 2
models:
- name: orders
  columns:
  - name: order_id
    data_tests:
    - not_null
    - unique
  - name: total_amount
    data_tests:
    - dbt_utils.expression_is_true:
        arguments:
          expression: ">= 0.00"
    - dbt_utils.expression_is_true:
        arguments:
          expression: "<= 500.00"
```

- dbt 1.10.5 or later is required for nested test `arguments`;
- numeric bounds are emitted **unquoted** even when the contract stores
  them as strings for precision;
- `range` requires the `dbt_utils` package;
- rule types without a dbt equivalent (e.g. `freshness`) are listed in the
  file header as comments - they do not disappear silently.

## Great Expectations

```json
{
  "suites": [
    {
      "name": "orders.suite",
      "expectations": [
        {"type": "expect_column_values_to_not_be_null",
         "kwargs": {"column": "order_id"},
         "meta": {"severity": "high", "source": "dq-doctor"}}
      ],
      "meta": {"unmapped_rule_ids": []}
    }
  ]
}
```

Load each entry with `gx.ExpectationSuite(**entry)`, then register the suite
with `context.suites.add(suite)`.

## SodaCL

```yaml
checks for orders:
  - missing_count(order_id) = 0
  - duplicate_count(order_id) = 0
  - invalid_count(status) = 0:
      valid values: ['paid', 'refunded']
  - min(total_amount) >= 0.00
  - max(total_amount) <= 500.00
  - freshness(created_at) < 24h
```

0.7 emitted an inline `{ values: [...] }` map that SodaCL does not
recognize.

## Deequ

Deequ has no official JSON interchange format. This export is a
**pydeequ constraint plan**:

```json
{"version": "1.0", "datasets": [{"dataset": "orders", "engine": "pydeequ",
  "checks": [{"constraint": "HasCompleteness",
              "kwargs": {"column": "order_id"},
              "rule_id": "orders/not_null:order_id"}]}]}
```

## Markdown

A table per model listing rule id, type, column, severity, params and
enabled flag (disabled rules stay visible).

## Unmapped rules

Rule types without an equivalent in the target never vanish:

| Exporter | Where unmapped rules appear |
|---|---|
| dbt | `#` comment block at the top of the file |
| GX | `meta.unmapped_rule_ids` |
| Soda | `# unmapped rules` comment block |
| Deequ | `unmapped_rule_ids` per dataset |
| markdown | full table (nothing is dropped) |
