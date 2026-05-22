# Custom SQL Rules

Write your own validation queries that run alongside built-in rules.

## In Config File

```yaml
# .dqdoctor.yml
tables:
  orders:
    sql_rules:
      - name: no_negative_amount
        query: "SELECT COUNT(*) FROM orders WHERE total_amount < 0"
        expect: 0

      - name: valid_status_transition
        query: "SELECT COUNT(*) FROM orders WHERE status = 'unknown'"
        expect: 0
```

Each rule has:
- `name` — rule identifier
- `query` — SQL that returns a single number
- `expect` — expected value (pass if result equals this)

## Generate Editable Rules

```bash
dqdoctor rules-init --db demo.duckdb --table orders --out rules.yml
```

This creates a YAML file with all auto-generated rules. Edit it to:

- Set `enabled: false` to disable rules
- Change `severity`
- Modify `params`

Then run with your rules:

```bash
dqdoctor check --db demo.duckdb --table orders --rules rules.yml
```

## How It Works

1. Auto-generated rules run first (from profiling)
2. Config rules apply (disable, severity override)
3. Custom rules from `--rules` file are merged
4. SQL rules from config execute last
5. All results go into the HTML report
