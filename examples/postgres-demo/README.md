# PostgreSQL Demo — dq-doctor

## Prerequisites

```bash
pip install dq-doctor[sql]
docker compose up -d
```

## Run

Wait for Postgres to be ready (~10s), then:

```bash
# List tables
dqdoctor tables --db "postgresql://dquser:dqpass@localhost:5432/dqdemo"

# Profile
dqdoctor profile --db "postgresql://dquser:dqpass@localhost:5432/dqdemo" --table orders

# Full check
dqdoctor check --db "postgresql://dquser:dqpass@localhost:5432/dqdemo" --table orders --out report.html
```

## Cleanup

```bash
docker compose down -v
```
