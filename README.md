# dq-doctor

One command to profile tables, generate data quality checks, and catch dirty data.

一行命令，完成数据质量体检。

**[English](#highlights)** | **[中文](#核心功能)**

[![PyPI](https://img.shields.io/pypi/v/dq-doctor)](https://pypi.org/project/dq-doctor/)
[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue)](https://pypi.org/project/dq-doctor/)
[![Tests](https://img.shields.io/badge/tests-109%20passed-green)](https://github.com/pugyy/dq-doctor)
[![License: MIT](https://img.shields.io/badge/license-MIT-yellow)](https://github.com/pugyy/dq-doctor/blob/main/LICENSE)

```bash
pip install dq-doctor
dqdoctor demo --dirty
dqdoctor check --db dirty.duckdb --all-tables --out report.html
```

```
dirty_orders: Score 82/100  Rules 13  Passed 12  Failed 1
  FAIL not_null on user_id: Found 3/20 nulls.
  ORPHAN dirty_orders.user_id -> dirty_users.user_id: 2/17 orphans
  PII detected: email in 'email', phone_cn in 'phone'
```

---

## Highlights

- **Zero config** — profile, generate rules, validate, output HTML in one command
- **Quality Score** — 0-100 score per table, based on rule pass rate + PII + referential integrity
- **Dirty data demo** — `dqdoctor demo --dirty` creates a database with intentional issues
- **PII detection** — flags emails, phone numbers, ID cards in your columns
- **Referential integrity** — finds orphan rows across tables
- **5 export formats** — dbt, Great Expectations, Soda CL, Deequ, Markdown
- **PostgreSQL / MySQL** — DuckDB first-class, PG/MySQL via connection string
- **Custom SQL rules** — write your own validation queries
- **Editable rules file** — `dqdoctor rules-init` generates a YAML you can edit, disable, override
- **LLM suggestions** — optional AI-powered rule generation (experimental)

## Quick Start

```bash
pip install dq-doctor

# Generate a demo database with data quality issues
dqdoctor demo --dirty

# Run a full check
dqdoctor check --db dirty.duckdb --all-tables --out report.html

# Open the report
open report.html       # macOS
start report.html      # Windows
```

## Commands

```bash
dqdoctor doctor                                          # Check your installation
dqdoctor tables --db demo.duckdb                         # List tables
dqdoctor profile --db demo.duckdb --table orders         # Profile + PII detection
dqdoctor check --db demo.duckdb --table orders --out report.html  # Full check
dqdoctor check --db demo.duckdb --all-tables             # Check all tables
dqdoctor rules-init --db demo.duckdb --table orders --out rules.yml  # Editable rules
dqdoctor fk --db demo.duckdb                             # Discover foreign keys
dqdoctor refint --db demo.duckdb                         # Check referential integrity
dqdoctor drift --old v1.json --new v2.json               # Compare profile drift
dqdoctor export --format dbt --out schema.yml            # Export rules
dqdoctor init                                            # Generate .dqdoctor.yml
```

## How It Works

```
Your Database (DuckDB / PostgreSQL / MySQL)
  │
  ├─ Profile columns (types, null rates, distributions, PII detection)
  ├─ Auto-generate rules (not_null, unique, accepted_values, range, freshness)
  ├─ Validate rules against your data
  ├─ Check referential integrity (orphan detection)
  ├─ Compute Quality Score (0-100)
  └─ Output HTML report + optional exports
```

Every rule comes with a human-readable reason — you know *why* it was suggested, not just *what* it checks.

## Supported Rules

| Rule | Trigger | Example |
|------|---------|---------|
| `not_null` | Column has zero nulls, or is an identifier field | `order_id` has no nulls |
| `unique` | Identifier field with >= 98% distinct rate | `user_id` is nearly unique |
| `accepted_values` | Category field with <= 20 distinct values | `status` has 4 values |
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

Full reference: [docs/config.md](docs/config.md)

## Export Formats

```bash
dqdoctor export --format dbt --out schema.yml          # dbt schema.yml
dqdoctor export --format gx --out suite.json           # Great Expectations
dqdoctor export --format soda --out checks.yml         # Soda CL
dqdoctor export --format deequ --out checks.json       # Deequ
dqdoctor export --format markdown --out dict.md        # Markdown
```

## PostgreSQL / MySQL

```bash
pip install dq-doctor[sql]
dqdoctor check --db "postgresql://user:pass@host:5432/dbname" --table orders
dqdoctor check --db "mysql://user:pass@host:3306/dbname" --table orders
```

Docker examples: [examples/postgres-demo/](examples/postgres-demo/) · [examples/mysql-demo/](examples/mysql-demo/)

## LLM-Enhanced Rules (Experimental)

```bash
pip install dq-doctor[llm]
dqdoctor check --db demo.duckdb --table orders \
  --llm-key "sk-xxx" \
  --llm-base-url "https://api.deepseek.com/v1" \
  --llm-model "deepseek-chat"
```

LLM rules appear as **SUGGEST** status — separate from pass/fail counts.

## CI Mode

```bash
dqdoctor check --db demo.duckdb --table orders --ci --max-failures 0
```

Exits with code 1 when rule failures or referential integrity issues exceed threshold.

## Documentation

- [Quick Start](docs/quickstart.md)
- [Configuration](docs/config.md)
- [Custom SQL Rules](docs/custom-sql-rules.md)
- [PostgreSQL / MySQL](docs/postgres-mysql.md)
- [Export Formats](docs/exporters.md)
- [Dirty Demo Walkthrough](docs/dirty-demo.md)
- [Architecture](docs/architecture.md)
- [Limitations](docs/limitations.md)

## Development

```bash
git clone https://github.com/pugyy/dq-doctor.git
cd dq-doctor
pip install -e ".[dev]"
pytest tests/ -v    # 109 tests
ruff check .        # lint
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

---

## 核心功能

dq-doctor 是一个轻量级数据质量体检 CLI 工具。一行命令完成表结构分析、质量规则生成、校验和 HTML 报告。

- **零配置** — 一行命令完成 profiling + 规则生成 + 校验 + HTML 报告
- **质量评分** — 每张表 0-100 分，综合规则通过率、PII、参照完整性
- **脏数据演示** — `dqdoctor demo --dirty` 生成带问题的数据库，直接看效果
- **PII 检测** — 自动识别邮箱、手机号、身份证等敏感字段
- **参照完整性** — 发现跨表孤立记录（orphan rows）
- **5 种导出格式** — dbt / GX / Soda CL / Deequ / Markdown
- **多数据库** — DuckDB 一等支持，PostgreSQL / MySQL 通过连接字符串
- **自定义 SQL 规则** — 编写自己的校验查询
- **可编辑规则** — `dqdoctor rules-init` 生成 YAML，支持禁用、改 severity、覆盖参数
- **LLM 建议** — 可选 AI 规则生成（实验性）

### 30 秒体验

```bash
pip install dq-doctor
dqdoctor demo --dirty
dqdoctor check --db dirty.duckdb --all-tables --out report.html
```

### 配置文件

```bash
dqdoctor init  # 生成 .dqdoctor.yml
```

支持：禁用规则、覆盖 severity、自定义 SQL 规则、freshness 覆盖。详见 [docs/config.md](docs/config.md)。

### CI 模式

```bash
dqdoctor check --db demo.duckdb --table orders --ci --max-failures 0
```

规则失败或参照完整性问题超过阈值时退出码为 1。

### 实验性功能

| 功能 | 状态 |
|------|------|
| LLM 规则建议 | 质量取决于模型 |
| 列相关性 | 仅 Pearson |
| 数据血缘 | 基于启发式（FK + 相关性） |
| Soda CL / Deequ 导出 | 基础指标映射 |
| Web 看板 | 只读 |

---

## Changelog

### v0.7.1
- Fix: `--ci` now counts referential integrity failures
- Fix: Quality Score display (extra `]` removed)
- Fix: `--verbose-rules` shows config disable/severity overrides
- Tests: 109 passing

### v0.7.0
- Quality Score (0-100) per table in CLI and HTML report
- PII detection and referential integrity integrated into HTML report
- New `--verbose-rules` flag to show rule sources and overrides

### v0.6.3
- Custom rules now override auto rules (params/severity/disable)
- `rules-init` Decimal serialization fixed
- doctor command: optional deps no longer trigger core failure

### v0.6.0
- README redesigned with badges and clear first screen
- Full documentation split into `docs/` (8 pages)
- Examples: dirty-demo, postgres-demo (docker-compose), mysql-demo (docker-compose)
- CONTRIBUTING.md added
- `dqdoctor doctor` health check command
- `dqdoctor rules-init` editable rules file
- `--save-profile` for drift comparison workflow

### v0.5.0
- Usability release: docs, examples, doctor, rules-init, save-profile

### v0.4.0
- `.dqdoctor.yml` configuration file
- Custom SQL rules
- Referential integrity checker
- GitHub Actions PG/MySQL CI
- Dirty demo dataset

### v0.3.0
- PII detection, FK discovery, column correlation, data lineage
- Profile drift comparison
- Soda CL and Deequ export
- Flask dashboard, Airflow operator

### v0.2.0
- ConnectionWrapper (DuckDB/PG/MySQL)
- dbt native format export
- LLM-enhanced rules
- 66 tests

### v0.1.0
- Initial release: 5 heuristic rules, HTML reports, export to dbt/GX/Markdown
- 53 tests, PyPI published

---

## License

MIT
