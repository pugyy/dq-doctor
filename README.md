<div align="center">

# 🩺 dq-doctor

**一行命令，完成数据质量体检。**

**One command to profile tables, generate data quality checks, and catch dirty data.**

[![PyPI](https://img.shields.io/pypi/v/dq-doctor?color=blue&label=PyPI)](https://pypi.org/project/dq-doctor/)
[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-3776AB?logo=python&logoColor=white)](https://pypi.org/project/dq-doctor/)
[![Tests](https://img.shields.io/badge/tests-109%20passed-4CAF50?logo=pytest)](https://github.com/pugyy/dq-doctor)
[![License: MIT](https://img.shields.io/badge/license-MIT-FDD835?logo=opensourceinitiative&logoColor=black)](https://github.com/pugyy/dq-doctor/blob/main/LICENSE)
[![GitHub stars](https://img.shields.io/github/stars/pugyy/dq-doctor?style=social)](https://github.com/pugyy/dq-doctor)

</div>

---

```bash
pip install dq-doctor
dqdoctor demo --dirty
dqdoctor check --db dirty.duckdb --all-tables --out report.html
```

```
dirty_orders: Score 82/100  Rules 13  Passed 12  Failed 1
  FAIL not_null on user_id: Found 3/20 nulls in 'user_id'.
  ORPHAN dirty_orders.user_id -> dirty_users.user_id: 2/17 orphans
  PII detected: email in column 'email', phone_cn in column 'phone'
```

---

## ✨ Highlights / 亮点

| English | 中文 |
|---------|------|
| **Zero config** — profile, generate rules, validate, HTML report in one command | **零配置** — 一行命令完成 profiling + 规则生成 + 校验 + HTML 报告 |
| **Quality Score** — each table gets a 0–100 score based on rule pass rate, PII, and referential integrity | **质量评分** — 每张表获得 0–100 评分，综合规则通过率、PII、参照完整性 |
| **Dirty data demo** — `dqdoctor demo --dirty` generates a database with intentional issues | **脏数据演示** — `dqdoctor demo --dirty` 自动生成带问题的数据库 |
| **PII detection** — flags emails, phone numbers, ID cards in your columns | **PII 检测** — 自动识别邮箱、手机号、身份证等敏感字段 |
| **Referential integrity** — finds orphan rows across tables, integrated into reports and CI | **参照完整性** — 发现跨表孤立记录，集成到报告和 CI |
| **5 export formats** — dbt, Great Expectations, Soda CL, Deequ, Markdown | **5 种导出格式** — dbt / GX / Soda CL / Deequ / Markdown |
| **PostgreSQL / MySQL** — DuckDB first-class, PG/MySQL via connection string | **多数据库支持** — DuckDB 一等支持，PG/MySQL 通过连接字符串 |
| **Custom SQL rules** — write your own validation queries | **自定义 SQL 规则** — 编写自己的校验查询 |
| **Editable rules file** — `dqdoctor rules-init` generates a YAML you can edit, disable, override | **可编辑规则文件** — `dqdoctor rules-init` 生成 YAML，支持禁用和覆盖 |
| **LLM suggestions** — optional AI-powered rule generation (experimental) | **LLM 建议** — 可选的 AI 规则生成（实验性） |

---

## 🚀 Quick Start / 快速开始

**English:**

```bash
pip install dq-doctor

# Generate a demo database with intentional data quality issues
dqdoctor demo --dirty

# Run a full check — outputs HTML report with quality score
dqdoctor check --db dirty.duckdb --all-tables --out report.html

# Open the report
open report.html       # macOS
start report.html      # Windows
```

**中文：**

```bash
pip install dq-doctor

# 生成一个带数据质量问题的演示数据库
dqdoctor demo --dirty

# 运行完整检查 — 输出带质量评分的 HTML 报告
dqdoctor check --db dirty.duckdb --all-tables --out report.html

# 打开报告
open report.html       # macOS
start report.html      # Windows
```

That's it. Three commands to see dq-doctor in action. / 三行命令即可体验。

---

## 📋 All Commands / 全部命令

| Command / 命令 | Description / 说明 |
|----------------|---------------------|
| `dqdoctor doctor` | Health check your installation / 检查安装是否完整 |
| `dqdoctor tables --db demo.duckdb` | List tables / 列出所有表 |
| `dqdoctor profile --db demo.duckdb --table orders` | Profile a table + PII detection / 分析表 + PII 检测 |
| `dqdoctor check --db demo.duckdb --table orders --out report.html` | Full check: profile + rules + validate + report / 完整检查 |
| `dqdoctor check --db demo.duckdb --all-tables` | Check all tables / 检查所有表 |
| `dqdoctor rules-init --db demo.duckdb --table orders --out rules.yml` | Generate editable rules file / 生成可编辑规则文件 |
| `dqdoctor fk --db demo.duckdb` | Discover foreign keys / 发现外键关系 |
| `dqdoctor refint --db demo.duckdb` | Check referential integrity / 检查参照完整性 |
| `dqdoctor drift --old v1.json --new v2.json` | Compare profiles for drift / 对比 profile 漂移 |
| `dqdoctor export --format dbt --out schema.yml` | Export rules / 导出规则 |
| `dqdoctor init` | Generate config file / 生成配置文件 |

---

## 🎯 What It Does / 功能概览

```
DuckDB (first-class) / PostgreSQL / MySQL
  → Profile table structure & column distributions          → 分析表结构和字段分布
  → Auto-generate quality rules (5 types)                   → 自动生成 5 种质量规则
  → Execute validations + custom SQL rules                  → 执行校验 + 自定义 SQL 规则
  → PII detection (email, phone, ID card, IP, etc.)         → PII 敏感数据检测
  → Cross-table FK discovery & referential integrity        → 跨表外键发现 + 参照完整性
  → Column correlation & data lineage                       → 列相关性 + 数据血缘
  → Profile drift comparison                                → Profile 漂移对比
  → Quality Score (0–100) per table                         → 每张表的质量评分
  → Output HTML report                                      → 输出 HTML 报告
  → Export to dbt / GX / Soda CL / Deequ / Markdown         → 5 种格式导出
```

---

## 📊 Supported Rules / 支持的规则

| Rule / 规则 | Trigger / 触发条件 | Example / 示例 |
|-------------|-------------------|----------------|
| `not_null` | Column has zero nulls, or is an identifier field | `order_id` has no nulls / 无空值 |
| `unique` | Identifier field with ≥98% distinct rate | `user_id` is nearly unique / 近乎唯一 |
| `accepted_values` | Category field with ≤20 distinct values | `status` has 4 values / 4 个枚举值 |
| `range` | Numeric column | `total_amount` in [45, 680] |
| `freshness` | Timestamp field | `created_at` within 24h / 24 小时以内 |

---

## ⚙️ Configuration / 配置文件

```bash
dqdoctor init                          # Create .dqdoctor.yml / 生成配置文件
dqdoctor check --config .dqdoctor.yml  # Use config / 使用配置
```

```yaml
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

See [docs/config.md](docs/config.md) for full reference. / 详见 [docs/config.md](docs/config.md)。

---

## 📤 Export Formats / 导出格式

| Format | Command |
|--------|---------|
| dbt schema.yml | `dqdoctor export --format dbt --out schema.yml` |
| Great Expectations | `dqdoctor export --format gx --out suite.json` |
| Soda CL | `dqdoctor export --format soda --out checks.yml` |
| Deequ | `dqdoctor export --format deequ --out checks.json` |
| Markdown | `dqdoctor export --format markdown --out dict.md` |

---

## 🐘 PostgreSQL / MySQL

```bash
pip install dq-doctor[sql]
dqdoctor check --db "postgresql://user:pass@host:5432/dbname" --table orders
dqdoctor check --db "mysql://user:pass@host:3306/dbname" --table orders
```

Docker setups: [examples/postgres-demo/](examples/postgres-demo/) · [examples/mysql-demo/](examples/mysql-demo/)

---

## 🤖 LLM-Enhanced Rules / LLM 增强规则 (Experimental / 实验性)

```bash
pip install dq-doctor[llm]
dqdoctor check --db demo.duckdb --table orders \
  --llm-key "sk-xxx" \
  --llm-base-url "https://api.deepseek.com/v1" \
  --llm-model "deepseek-chat"
```

LLM rules appear as **SUGGEST** status (not validated) — separate from pass/fail counts.

LLM 规则显示为 **SUGGEST** 状态（未实际校验），与通过/失败的规则分开统计。

---

## 🔧 CI Mode / CI 模式

```bash
dqdoctor check --db demo.duckdb --table orders --ci --max-failures 0
```

Exits with code 1 when rule failures **or** referential integrity issues exceed threshold.

规则失败或参照完整性问题超过阈值时，退出码为 1。

---

## ⚠️ Experimental Features / 实验性功能

| Feature / 功能 | Status / 状态 |
|----------------|---------------|
| LLM rule suggestions / LLM 规则建议 | Experimental — quality depends on model / 质量取决于模型 |
| Column correlation / 列相关性 | Experimental — Pearson only / 仅 Pearson |
| Data lineage / 数据血缘 | Experimental — heuristic-based / 基于启发式 |
| Soda CL / Deequ export | Starter — basic metric mapping / 基础指标映射 |
| Web dashboard / Web 看板 | Starter — read-only / 只读 |

See [docs/limitations.md](docs/limitations.md) for details. / 详见 [docs/limitations.md](docs/limitations.md)。

---

## 📚 Documentation / 文档

| Doc / 文档 | Description / 说明 |
|------------|---------------------|
| [Quick Start](docs/quickstart.md) | 30-second setup / 30 秒上手 |
| [Configuration](docs/config.md) | .dqdoctor.yml reference / 配置文件参考 |
| [Custom SQL Rules](docs/custom-sql-rules.md) | Write your own validation queries / 自定义校验查询 |
| [PostgreSQL / MySQL](docs/postgres-mysql.md) | Connect to real databases / 连接真实数据库 |
| [Export Formats](docs/exporters.md) | dbt, GX, Soda, Deequ, Markdown |
| [Dirty Demo Walkthrough](docs/dirty-demo.md) | 3-minute guided demo / 3 分钟引导演示 |
| [Architecture](docs/architecture.md) | Data flow and project structure / 数据流和项目结构 |
| [Limitations](docs/limitations.md) | Known limitations / 已知限制 |

---

## 🤝 Contributing / 贡献

See [CONTRIBUTING.md](CONTRIBUTING.md). / 详见 [CONTRIBUTING.md](CONTRIBUTING.md)。

---

## 🛠️ Development / 开发

```bash
git clone https://github.com/pugyy/dq-doctor.git
cd dq-doctor
pip install -e ".[dev]"

pytest tests/ -v    # 109 tests
ruff check .        # lint
```

---

## 🗺️ Roadmap / 路线图

- [x] DuckDB + PostgreSQL / MySQL support / 多数据库支持
- [x] PII detection, FK discovery, referential integrity / PII 检测、外键发现、参照完整性
- [x] Configuration file + custom SQL rules / 配置文件 + 自定义 SQL 规则
- [x] Quality Score + integrated report (PII, refint) / 质量评分 + 集成报告
- [x] Editable rules file (`dqdoctor rules-init`) / 可编辑规则文件
- [x] Profile drift comparison + data lineage / 漂移对比 + 数据血缘
- [x] Export: dbt / GX / Soda CL / Deequ / Markdown / 5 种格式导出
- [x] Dirty demo + web dashboard + Airflow operator / 脏数据演示 + 看板 + Airflow
- [x] PyPI published / 已发布到 PyPI (v0.7.1)
- [ ] Demo GIF / 演示动图

---

## 📄 License / 许可证

[MIT](https://github.com/pugyy/dq-doctor/blob/main/LICENSE)
