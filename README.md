# dq-doctor

**One command to profile tables, generate data quality checks, and catch dirty data.**

[![PyPI](https://img.shields.io/pypi/v/dq-doctor)](https://pypi.org/project/dq-doctor/)
[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue)](https://pypi.org/project/dq-doctor/)
[![Tests](https://img.shields.io/badge/tests-105%20passed-green)](https://github.com/pugyy/dq-doctor)
[![License: MIT](https://img.shields.io/badge/license-MIT-yellow)](https://github.com/pugyy/dq-doctor/blob/main/LICENSE)

```bash
pip install dq-doctor
dqdoctor demo --dirty
dqdoctor check --db dirty.duckdb --all-tables --out report.html
```

![dq-doctor report screenshot](docs/screenshot.png)

## Highlights

- **Zero config** — profile, generate rules, validate, output HTML in one command
- **Dirty data demo** — `dqdoctor demo --dirty` generates a database with intentional issues
- **PII detection** — flags emails, phone numbers, ID cards in your columns
- **Referential integrity** — finds orphan rows across tables
- **5 export formats** — dbt, Great Expectations, Soda CL, Deequ, Markdown
- **PostgreSQL / MySQL** — DuckDB first-class, PG/MySQL via connection string
- **Custom SQL rules** — write your own validation queries
- **LLM suggestions** — optional AI-powered rule generation (experimental)

[English](#quick-start) | [中文说明](#中文说明)

## Quick Start

```bash
pip install dq-doctor

# Try it now — generates a demo database with data quality issues
dqdoctor demo --dirty

# Run a full check
dqdoctor check --db dirty.duckdb --all-tables --out report.html

# Open the report
open report.html       # macOS
start report.html      # Windows
```

That's it. Three commands to see dq-doctor in action.

## All Commands

```bash
# Health check your installation
dqdoctor doctor

# List tables
dqdoctor tables --db demo.duckdb

# Profile a table (column stats + PII detection)
dqdoctor profile --db demo.duckdb --table orders

# Full check: profile + rules + validate + HTML report
dqdoctor check --db demo.duckdb --table orders --out report.html

# Check all tables
dqdoctor check --db demo.duckdb --all-tables --out report.html

# Generate editable rules file
dqdoctor rules-init --db demo.duckdb --table orders --out rules.yml

# Discover foreign keys across tables
dqdoctor fk --db demo.duckdb

# Check referential integrity (orphan detection)
dqdoctor refint --db demo.duckdb

# Compare profiles for drift
dqdoctor profile --db demo.duckdb --table orders --out v1.json
dqdoctor profile --db demo.duckdb --table orders --out v2.json
dqdoctor drift --old v1.json --new v2.json

# Export to dbt / GX / Soda / Deequ / Markdown
dqdoctor export --db demo.duckdb --table orders --format dbt --out schema.yml

# Generate config file
dqdoctor init
```

## What It Does

```
DuckDB (first-class) / PostgreSQL / MySQL
  → Profile table structure & column distributions
  → Auto-generate quality rules (not_null, unique, accepted_values, range, freshness)
  → Execute validations + custom SQL rules
  → PII detection (email, phone, ID card, IP, etc.)
  → Cross-table FK discovery & referential integrity checks
  → Column correlation detection
  → Profile drift comparison
  → Output HTML report
  → Export to dbt / GX / Soda CL / Deequ / Markdown
```

**Every rule comes with a human-readable reason** — so you know *why* the rule was suggested, not just *what* it checks.

## Example Output

```
dirty_orders: Rules 13  Passed 12  Failed 1  Suggested 0
  PASS not_null on order_id: All 20 rows have non-null 'order_id'.
  FAIL not_null on user_id: 3 rows have null 'user_id'.
  PASS unique on order_id: All 20 values are unique.
  PASS range on total_amount: All 20 values within [-200.00, 99999.99].
  PASS accepted_values on status: All non-null values in accepted set.
  PASS freshness on created_at: Latest value is 1.0h old (max 24h).

  PII detected:
    email in column 'email'
    phone_cn in column 'phone'

Use dqdoctor refint to find orphan rows (e.g. user_id=99 references a non-existent user).
```

## Supported Rules

| Rule | How It's Triggered | Example |
|------|--------------------|---------|
| `not_null` | Column has zero nulls, or is an identifier field | `order_id` has no nulls |
| `unique` | Identifier field with ≥98% distinct rate | `user_id` is nearly unique |
| `accepted_values` | Category field with ≤20 distinct values | `status` has 4 values |
| `range` | Numeric column | `total_amount` in [45.00, 680.00] |
| `freshness` | Timestamp field | `created_at` within 24h |

## Configuration

```bash
dqdoctor init                          # Create .dqdoctor.yml
dqdoctor check --config .dqdoctor.yml  # Use config
```

```yaml
# .dqdoctor.yml
db: demo.duckdb
tables:
  orders:
    disable_rules: [range:user_id]
    severity:
      order_id:not_null: high
    sql_rules:
      - name: amount_positive
        query: "SELECT COUNT(*) FROM orders WHERE total_amount <= 0"
        expect: 0
```

See [docs/config.md](docs/config.md) for full reference.

## Export Formats

| Format | Command |
|--------|---------|
| dbt schema.yml | `dqdoctor export --format dbt --out schema.yml` |
| Great Expectations | `dqdoctor export --format gx --out suite.json` |
| Soda CL | `dqdoctor export --format soda --out checks.yml` |
| Deequ | `dqdoctor export --format deequ --out checks.json` |
| Markdown | `dqdoctor export --format markdown --out dict.md` |

## PostgreSQL / MySQL

```bash
pip install dq-doctor[sql]
dqdoctor check --db "postgresql://user:pass@host:5432/dbname" --table orders
dqdoctor check --db "mysql://user:pass@host:3306/dbname" --table orders
```

See [examples/postgres-demo/](examples/postgres-demo/) and [examples/mysql-demo/](examples/mysql-demo/) for docker-compose setups.

## LLM-Enhanced Rules (Experimental)

```bash
pip install dq-doctor[llm]
dqdoctor check --db demo.duckdb --table orders \
  --llm-key "sk-xxx" \
  --llm-base-url "https://api.deepseek.com/v1" \
  --llm-model "deepseek-chat"
```

LLM rules appear as **SUGGEST** status (not validated) — separate from pass/fail counts.

## CI Mode

```bash
dqdoctor check --db demo.duckdb --table orders --ci --max-failures 0
```

Exits with code 1 when failures exceed threshold.

## Experimental Features

| Feature | Status |
|---------|--------|
| LLM rule suggestions | Experimental — quality depends on model |
| Column correlation | Experimental — Pearson only |
| Data lineage | Experimental — FK + correlation heuristics |
| Soda CL / Deequ export | Starter — basic metric mapping |
| Web dashboard | Starter — read-only |

See [docs/limitations.md](docs/limitations.md) for details.

## Documentation

- [Quick Start](docs/quickstart.md)
- [Configuration](docs/config.md)
- [Custom SQL Rules](docs/custom-sql-rules.md)
- [PostgreSQL / MySQL](docs/postgres-mysql.md)
- [Export Formats](docs/exporters.md)
- [Dirty Demo Walkthrough](docs/dirty-demo.md)
- [Architecture](docs/architecture.md)
- [Limitations](docs/limitations.md)

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## 中文说明

dq-doctor 是一个轻量级数据质量体检 CLI 工具。一行命令，自动 profile 表结构、生成质量规则、执行校验并输出 HTML 报告。

![dq-doctor 报告截图](docs/screenshot.png)

### 30 秒体验

```bash
pip install dq-doctor
dqdoctor demo --dirty
dqdoctor check --db dirty.duckdb --all-tables --out report.html
```

### 核心特性

- **零配置** — 一行命令完成 profile + 规则生成 + 校验 + 报告
- **脏数据 Demo** — `dqdoctor demo --dirty` 自动生成带问题的数据库
- **PII 检测** — 自动识别邮箱、手机号、身份证等敏感字段
- **参照完整性** — 发现跨表孤立记录
- **5 种导出格式** — dbt / GX / Soda CL / Deequ / Markdown
- **PostgreSQL / MySQL** — 通过连接字符串直接连
- **自定义 SQL 规则** — 写自己的校验查询
- **LLM 建议** — 可选的 AI 规则生成（实验性）

### 配置文件

```bash
dqdoctor init  # 生成 .dqdoctor.yml
```

### CI 模式

```bash
dqdoctor check --db demo.duckdb --table orders --ci --max-failures 0
```

### 技术栈

Python 3.9+ / Typer / DuckDB / Pydantic / Jinja2 / Rich

## Development

```bash
git clone https://github.com/pugyy/dq-doctor.git
cd dq-doctor
pip install -e ".[dev]"

pytest tests/ -v    # 101 tests
ruff check .        # lint
```

## Roadmap

- [x] DuckDB + PostgreSQL / MySQL support
- [x] PII detection, FK discovery, referential integrity
- [x] Configuration file + custom SQL rules
- [x] Profile drift comparison + data lineage
- [x] Export: dbt / GX / Soda CL / Deequ / Markdown
- [x] Dirty demo + web dashboard + Airflow operator
- [x] `dqdoctor doctor` health check
- [x] `dqdoctor rules-init` editable rules
- [x] PyPI published (v0.5.0)
- [ ] Demo GIF

## License

MIT
