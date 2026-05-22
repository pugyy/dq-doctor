# PostgreSQL / MySQL Support

dq-doctor supports PostgreSQL and MySQL via SQLAlchemy.

## Install

```bash
pip install dq-doctor[sql]
```

This installs SQLAlchemy, psycopg2 (PostgreSQL), and pymysql (MySQL).

## Connection Strings

```bash
# PostgreSQL
dqdoctor check --db "postgresql://user:pass@host:5432/dbname" --table orders

# MySQL
dqdoctor check --db "mysql://user:pass@host:3306/dbname" --table orders
```

## Try with Docker

See the example projects:

- [examples/postgres-demo/](../examples/postgres-demo/) — PostgreSQL with docker-compose
- [examples/mysql-demo/](../examples/mysql-demo/) — MySQL with docker-compose

```bash
cd examples/postgres-demo
docker compose up -d
pip install dq-doctor[sql]
dqdoctor tables --db "postgresql://dquser:dqpass@localhost:5432/dqdemo"
dqdoctor check --db "postgresql://dquser:dqpass@localhost:5432/dqdemo" --table orders --out report.html
```

## What Works

All features work the same across databases:

- Profiling (column stats, types, null rates)
- Rule generation and validation
- HTML reports
- PII detection
- FK discovery and referential integrity
- Export to dbt/GX/Soda/Deequ/Markdown

## Connection String in Config

```yaml
# .dqdoctor.yml
db: "postgresql://dquser:dqpass@localhost:5432/dqdemo"
```
