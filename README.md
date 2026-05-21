# dq-doctor

**Generate data quality reports from your database in minutes — no YAML, no rule syntax to remember.**

A lightweight CLI that profiles your database tables, auto-generates quality check rules, runs validations, and outputs an HTML report. One command, zero config.

![dq-doctor report screenshot](docs/screenshot.png)

[English](#quick-start) | [中文说明](#中文说明)

## Quick Start

```bash
# Install
pip install -e .

# Generate a demo database to try it out
dqdoctor demo

# List tables
dqdoctor tables --db examples/ecommerce/demo.duckdb

# Profile a table
dqdoctor profile --db examples/ecommerce/demo.duckdb --table orders

# Full check: profile + rules + validate + HTML report
dqdoctor check --db examples/ecommerce/demo.duckdb --table orders --out report.html

# Check all tables at once
dqdoctor check --db examples/ecommerce/demo.duckdb --all-tables --out report.html

# Export rules to dbt / Great Expectations / Markdown
dqdoctor export --db examples/ecommerce/demo.duckdb --table orders --format dbt --out schema.yml
dqdoctor export --db examples/ecommerce/demo.duckdb --table orders --format gx --out suite.json
dqdoctor export --db examples/ecommerce/demo.duckdb --table orders --format markdown --out dict.md
```

That's it. Open `report.html` in your browser.

## What It Does

```
DuckDB (first-class)
  → Profile table structure & column distributions
  → Auto-generate quality rules (not_null, unique, accepted_values, range, freshness)
  → Execute validations
  → Output HTML report
  → Export to dbt schema.yml / Great Expectations / Markdown
```

**Every rule comes with a human-readable reason** — so you know *why* the rule was suggested, not just *what* it checks.

## Example Output

```
orders: Rules 14  Passed 14  Failed 0
  PASS not_null on order_id: All 20 rows have non-null 'order_id'.
  PASS unique on order_id: All 20 values in 'order_id' are unique.
  PASS range on total_amount: All 20 values within [45.00, 680.00].
  PASS accepted_values on status: All 20 non-null values in accepted set.
  PASS freshness on created_at: Latest value is 3.0h old (max 24h).
```

## Supported Rules

| Rule | How It's Triggered | Example |
|------|--------------------|---------|
| `not_null` | Column has zero nulls, or is an identifier field | `order_id` has no nulls → require not_null |
| `unique` | Identifier field with ≥98% distinct rate | `user_id` is nearly unique → require unique |
| `accepted_values` | Category field with ≤20 distinct values | `status` has 4 values → constrain to that set |
| `range` | Numeric column | `total_amount` in [45.00, 680.00] |
| `freshness` | Timestamp field | `created_at` should be within 24h |

## Export Formats

```bash
# Starter dbt schema.yml with column tests
dqdoctor export --format dbt --out schema.yml

# Great Expectations Expectation Suite JSON
dqdoctor export --format gx --out suite.json

# Markdown data dictionary
dqdoctor export --format markdown --out dict.md
```

Note: dbt export generates a starter schema.yml structure. You may need to adjust test types (e.g. `range`) to match your dbt version and packages.

## LLM-Enhanced Rules (Experimental)

Pass an LLM API key to get additional business rules beyond the heuristic ones:

```bash
dqdoctor check --db demo.duckdb --table orders ^
  --llm-key "sk-xxx" ^
  --llm-base-url "https://api.deepseek.com/v1" ^
  --llm-model "deepseek-chat"
```

Without `--llm-key`, dqdoctor runs purely with deterministic heuristic rules. Requires `pip install dq-doctor[llm]`.

## CI Mode

Use in CI/CD pipelines — exits with code 1 when failures exceed threshold:

```bash
dqdoctor check --db demo.duckdb --table orders --ci --max-failures 0
```

## Why Not Great Expectations / Soda / dbt?

dq-doctor is **not** a replacement — it's a **quick checkup layer** that runs *before* you invest in heavy tooling:

- **Great Expectations / Soda**: Powerful but require YAML configs, expectation suites, and setup. dqdoctor gives you a first-pass report with zero config.
- **dbt tests**: Great for ongoing CI, but you need to write tests first. dqdoctor *suggests* tests for you and can export a starter schema.yml.
- **Think of it as**: `dqdoctor check` → discover issues → export to dbt/GX → refine.

## 中文说明

dqdoctor 是一个轻量级数据质量体检 CLI 工具。你不需要手写 YAML，不需要记 Great Expectations 或 dbt 的规则语法，只需要一行命令，就能对数据库表做 profiling、自动生成质量检查规则、执行校验并输出 HTML 报告。

**功能：**
- 自动 profiling 数据库表结构和字段分布
- 5 种确定性启发式质量规则，每条带可读的解释
- 导出 dbt schema.yml / Great Expectations / Markdown
- 可选 LLM 增强规则生成（实验性）
- CI/CD 模式，失败超阈值时 exit 1
- 开箱即用支持 DuckDB，PostgreSQL/MySQL 已规划

**适用人群：** 数据开发工程师、数仓工程师、数据平台实习生。

## Tech Stack

- Python 3.9+
- [Typer](https://typer.tiangolo.com/) — CLI framework
- [DuckDB](https://duckdb.org/) — embedded analytical database
- [Pydantic](https://docs.pydantic.dev/) — data models
- [Jinja2](https://jinja.palletsprojects.com/) — HTML report templates
- [Rich](https://rich.readthedocs.io/) — terminal output

## Development

```bash
git clone https://github.com/pugyy/dq-doctor.git
cd dq-doctor
pip install -e ".[dev]"

# Run tests (53 tests)
pytest tests/ -v

# Lint
ruff check dqdoctor/ tests/

# Try the demo
dqdoctor demo
dqdoctor check --db examples/ecommerce/demo.duckdb --table orders
```

## Roadmap

- [ ] PostgreSQL / MySQL real integration (connector framework exists)
- [ ] dbt schema.yml format refinement
- [ ] LLM-enhanced field interpretation (experimental)
- [ ] Demo GIF + screenshots
- [ ] PyPI publish

## License

MIT
