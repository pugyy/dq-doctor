# MySQL Demo — dq-doctor

## Prerequisites

```bash
pip install dq-doctor[sql]
docker compose up -d
```

## Run

Wait for MySQL to be ready (~15s), then:

```bash
# List tables
dqdoctor tables --db "mysql://dquser:dqpass@localhost:3306/dqdemo"

# Profile
dqdoctor profile --db "mysql://dquser:dqpass@localhost:3306/dqdemo" --table orders

# Full check
dqdoctor check --db "mysql://dquser:dqpass@localhost:3306/dqdemo" --table orders --out report.html
```

## Cleanup

```bash
docker compose down -v
```
