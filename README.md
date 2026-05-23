# dq-doctor

One command to profile tables, generate data quality checks, and catch dirty data.
一行命令，完成数据质量体检。

**[English](#highlights)** | **[中文](#核心功能)**

[![PyPI](https://img.shields.io/pypi/v/dq-doctor)](https://pypi.org/project/dq-doctor/)
[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue)](https://pypi.org/project/dq-doctor/)
[![CI](https://github.com/pugyy/dq-doctor/actions/workflows/ci.yml/badge.svg)](https://github.com/pugyy/dq-doctor/actions/workflows/ci.yml)
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

- **Zero config** — profile, generate rules, validate, output HTML in one command / 一行命令完成分析 + 规则生成 + 校验 + 报告
- **Quality Score** — 0-100 score per table, based on rule pass rate + PII + referential integrity / 每张表 0-100 评分
- **Dirty data demo** — `dqdoctor demo --dirty` creates a database with intentional issues / 生成带问题的演示数据库
- **PII detection** — flags emails, phone numbers, ID cards in your columns / 自动识别邮箱、手机号、身份证等敏感字段
- **Referential integrity** — finds orphan rows across tables / 发现跨表孤立记录
- **5 export formats** — dbt, Great Expectations, Soda CL, Deequ, Markdown / 5 种导出格式
- **PostgreSQL / MySQL** — DuckDB first-class, PG/MySQL via connection string / DuckDB 一等支持，PG/MySQL 通过连接字符串
- **Custom SQL rules** — write your own validation queries / 编写自己的校验查询
- **Editable rules file** — `dqdoctor rules-init` generates a YAML you can edit, disable, override / 生成可编辑规则文件
- **LLM suggestions** — optional AI-powered rule generation (experimental) / 可选 AI 规则生成（实验性）

## Quick Start / 快速开始

```bash
pip install dq-doctor

# Generate a demo database with data quality issues / 生成带数据质量问题的演示数据库
dqdoctor demo --dirty

# Run a full check / 运行完整检查
dqdoctor check --db dirty.duckdb --all-tables --out report.html

# Open the report / 打开报告
open report.html       # macOS
start report.html      # Windows
```

That's it. Three commands to see dq-doctor in action. / 三行命令即可体验。

## Commands / 命令

```bash
dqdoctor doctor                                          # Check installation / 检查安装
dqdoctor tables --db demo.duckdb                         # List tables / 列出表
dqdoctor profile --db demo.duckdb --table orders         # Profile + PII / 分析 + PII 检测
dqdoctor check --db demo.duckdb --table orders --out report.html  # Full check / 完整检查
dqdoctor check --db demo.duckdb --all-tables             # Check all / 检查所有表
dqdoctor rules-init --db demo.duckdb --table orders --out rules.yml  # Editable rules / 可编辑规则
dqdoctor fk --db demo.duckdb                             # Discover FK / 发现外键
dqdoctor refint --db demo.duckdb                         # Referential integrity / 参照完整性
dqdoctor drift --old v1.json --new v2.json               # Profile drift / 漂移对比
dqdoctor export --format dbt --out schema.yml            # Export rules / 导出规则
dqdoctor init                                            # Generate config / 生成配置文件
```

## How It Works / 工作原理

```
Your Database (DuckDB / PostgreSQL / MySQL)
  │
  ├─ Profile columns (types, null rates, distributions, PII detection)
  │   分析字段（类型、空值率、分布、PII 检测）
  ├─ Auto-generate rules (not_null, unique, accepted_values, range, freshness)
  │   自动生成 5 种质量规则
  ├─ Validate rules against your data
  │   对数据执行校验
  ├─ Check referential integrity (orphan detection)
  │   检查参照完整性（孤立记录检测）
  ├─ Compute Quality Score (0-100)
  │   计算质量评分
  └─ Output HTML report + optional exports
      输出 HTML 报告 + 可选导出
```

Every rule comes with a human-readable reason — you know *why* it was suggested, not just *what* it checks.
每条规则都有可读的原因说明——你知道为什么建议这个规则，而不仅仅是检查了什么。

## Supported Rules / 支持的规则

| Rule / 规则 | Trigger / 触发条件 | Example / 示例 |
|-------------|-------------------|----------------|
| `not_null` | Column has zero nulls, or is an identifier / 字段零空值或为标识符 | `order_id` has no nulls |
| `unique` | Identifier field with >= 98% distinct rate / 标识符字段唯一率 >= 98% | `user_id` is nearly unique |
| `accepted_values` | Category field with <= 20 distinct values / 分类字段不同值 <= 20 | `status` has 4 values |
| `range` | Numeric column / 数值字段 | `total_amount` in [45, 680] |
| `freshness` | Timestamp field / 时间戳字段 | `created_at` within 24h / 24 小时以内 |

## Configuration / 配置文件

```bash
dqdoctor init                          # Create .dqdoctor.yml / 生成配置文件
dqdoctor check --config .dqdoctor.yml  # Use config / 使用配置
```

```yaml
# .dqdoctor.yml
db: demo.duckdb
tables:
  orders:
    disable_rules: [range:user_id]      # 禁用规则
    severity:
      order_id:not_null: high           # 覆盖严重级别
    sql_rules:                           # 自定义 SQL 规则
      - name: amount_positive
        query: "SELECT COUNT(*) FROM orders WHERE total_amount <= 0"
        expect: 0
```

Full reference / 完整参考: [docs/config.md](docs/config.md)

## Export Formats / 导出格式

```bash
dqdoctor export --format dbt --out schema.yml          # dbt schema.yml
dqdoctor export --format gx --out suite.json           # Great Expectations
dqdoctor export --format soda --out checks.yml         # Soda CL
dqdoctor export --format deequ --out checks.json       # Deequ
dqdoctor export --format markdown --out dict.md        # Markdown / Markdown 数据字典
```

## PostgreSQL / MySQL

```bash
pip install dq-doctor[sql]
dqdoctor check --db "postgresql://user:pass@host:5432/dbname" --table orders
dqdoctor check --db "mysql://user:pass@host:3306/dbname" --table orders
```

Docker examples / Docker 示例: [examples/postgres-demo/](examples/postgres-demo/) · [examples/mysql-demo/](examples/mysql-demo/)

## LLM-Enhanced Rules / LLM 增强规则 (Experimental / 实验性)

```bash
pip install dq-doctor[llm]

# Replace --llm-key, --llm-base-url, --llm-model with your own API / 替换为你自己的 API 密钥、地址和模型
# Example below uses DeepSeek / 以下以 DeepSeek 为例
dqdoctor check --db demo.duckdb --table orders \
  --llm-key "sk-xxx" \
  --llm-base-url "https://api.deepseek.com/v1" \
  --llm-model "deepseek-chat"
```

LLM rules appear as **SUGGEST** status — separate from pass/fail counts.
LLM 规则显示为 **SUGGEST** 状态（未实际校验），与通过/失败的规则分开统计。

## CI Mode / CI 模式

```bash
dqdoctor check --db demo.duckdb --table orders --ci --max-failures 0
```

Exits with code 1 when rule failures or referential integrity issues exceed threshold.
规则失败或参照完整性问题超过阈值时，退出码为 1。

## Experimental Features / 实验性功能

| Feature / 功能 | Status / 状态 |
|----------------|---------------|
| LLM rule suggestions / LLM 规则建议 | Quality depends on model / 质量取决于模型 |
| Column correlation / 列相关性 | Pearson only / 仅 Pearson |
| Data lineage / 数据血缘 | Heuristic-based (FK + correlation) / 基于启发式 |
| Soda CL / Deequ export / 导出 | Basic metric mapping / 基础指标映射 |
| Web dashboard / Web 看板 | Read-only / 只读 |

Details / 详见: [docs/limitations.md](docs/limitations.md)

## Documentation / 文档

| Doc / 文档 | Description / 说明 |
|------------|---------------------|
| [Quick Start](docs/quickstart.md) | 30-second setup / 30 秒上手 |
| [Configuration](docs/config.md) | .dqdoctor.yml reference / 配置参考 |
| [Custom SQL Rules](docs/custom-sql-rules.md) | Write your own queries / 自定义校验查询 |
| [PostgreSQL / MySQL](docs/postgres-mysql.md) | Connect to real databases / 连接真实数据库 |
| [Export Formats](docs/exporters.md) | dbt, GX, Soda, Deequ, Markdown |
| [Dirty Demo](docs/dirty-demo.md) | Guided walkthrough / 引导演示 |
| [Architecture](docs/architecture.md) | Data flow & structure / 数据流和结构 |
| [Limitations](docs/limitations.md) | Known limits / 已知限制 |

## Development / 开发

```bash
git clone https://github.com/pugyy/dq-doctor.git
cd dq-doctor
pip install -e ".[dev]"
pytest tests/ -v    # 109 tests
ruff check .        # lint
```

See / 详见 [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines / 贡献指南。

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
- Fix: `--ci` now counts referential integrity failures / `--ci` 现在会计入参照完整性失败
- Fix: Quality Score display (extra `]` removed) / 质量评分显示修复
- Fix: `--verbose-rules` shows config disable/severity overrides / 显示配置禁用和严重级别覆盖
- Tests: 109 passing / 109 个测试通过

### v0.7.0
- Quality Score (0-100) per table in CLI and HTML report / CLI 和 HTML 报告新增质量评分
- PII detection and referential integrity integrated into HTML report / PII 检测和参照完整性集成到报告
- New `--verbose-rules` flag to show rule sources and overrides / 新增 `--verbose-rules` 显示规则来源

### v0.6.3
- Custom rules now override auto rules (params/severity/disable) / 自定义规则可覆盖自动规则
- `rules-init` Decimal serialization fixed / Decimal 序列化修复
- doctor command: optional deps no longer trigger core failure / doctor 可选依赖不再触发核心失败

### v0.6.0
- README redesigned with badges and clear first screen / README 重新设计
- Full documentation split into `docs/` (8 pages) / 文档拆分为 8 页
- Examples: dirty-demo, postgres-demo (docker-compose), mysql-demo (docker-compose) / 新增示例项目
- CONTRIBUTING.md added / 新增贡献指南
- `dqdoctor doctor` health check command / 新增安装健康检查
- `dqdoctor rules-init` editable rules file / 新增可编辑规则文件
- `--save-profile` for drift comparison workflow / 新增 profile 保存

### v0.5.0
- Usability release: docs, examples, doctor, rules-init, save-profile / 易用性发布

### v0.4.0
- `.dqdoctor.yml` configuration file / 配置文件
- Custom SQL rules / 自定义 SQL 规则
- Referential integrity checker / 参照完整性检查
- GitHub Actions PG/MySQL CI / GitHub Actions CI
- Dirty demo dataset / 脏数据演示

### v0.3.0
- PII detection, FK discovery, column correlation, data lineage / PII 检测、外键发现、相关性、数据血缘
- Profile drift comparison / 漂移对比
- Soda CL and Deequ export / Soda CL 和 Deequ 导出
- Flask dashboard, Airflow operator / Web 看板、Airflow 算子

### v0.2.0
- ConnectionWrapper (DuckDB/PG/MySQL) / 统一数据库连接
- dbt native format export / dbt 原生格式导出
- LLM-enhanced rules / LLM 增强规则
- 66 tests / 66 个测试

### v0.1.0
- Initial release: 5 heuristic rules, HTML reports, export to dbt/GX/Markdown / 初始发布
- 53 tests, PyPI published / 53 个测试，发布到 PyPI

---

## License / 许可证

[MIT](https://github.com/pugyy/dq-doctor/blob/main/LICENSE)
