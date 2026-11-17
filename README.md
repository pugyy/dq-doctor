<p align="center">
  <a href="#english"><b>English</b></a> &nbsp;·&nbsp; <a href="#简体中文"><b>简体中文</b></a>
</p>

<h1 align="center">dq-doctor</h1>

<p align="center">
  <b>Pin one data quality contract. Gate every new batch against it.</b><br>
  <sub>DuckDB · PostgreSQL · MySQL · CSV / Parquet / JSON · CLI · CI · Airflow · MCP</sub>
</p>

<p align="center">
  <a href="https://pypi.org/project/dq-doctor/"><img alt="PyPI" src="https://img.shields.io/pypi/v/dq-doctor"></a>
  <a href="https://pypi.org/project/dq-doctor/"><img alt="Python 3.12+" src="https://img.shields.io/badge/python-3.12%2B-blue"></a>
  <a href="https://github.com/pugyy/dq-doctor/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/pugyy/dq-doctor/actions/workflows/ci.yml/badge.svg"></a>
  <a href="https://github.com/pugyy/dq-doctor/blob/main/LICENSE"><img alt="License: MIT" src="https://img.shields.io/badge/license-MIT-yellow"></a>
  <a href="https://github.com/pugyy/dq-doctor"><img alt="Tests" src="https://img.shields.io/badge/tests-216%20passed%2C%2011%20skipped-brightgreen"></a>
</p>

```bash
pip install dq-doctor

dqdoctor demo --dirty
dqdoctor rules-init --db dirty.duckdb --all-tables --out contract.yml
dqdoctor check --db dirty.duckdb --all-tables --rules contract.yml --ci
```

```
dirty_orders  score 88/100  pass 12  fail 1
  FAIL dirty_orders/not_null:user_id: Found 3/20 nulls in 'user_id'.
  PII  email: email (8 samples)
  ORPHAN dirty_orders.user_id -> dirty_users.user_id: 2/17 (heuristic)
```

Exit `0` when clean or within policy, `1` when the quality gate trips, `2` on
input, configuration, connection or execution errors. Errors exit `2` whether
or not `--ci` is set.

---

<a id="english"></a>
## English

### Why dq-doctor

Most data quality tools ask you to write rules before you know what the data
looks like. dq-doctor works the other way around:

1. **Profile** a table and learn its shape (types, nulls, cardinality, ranges,
   enums, timestamp freshness, PII signals).
2. **Pin** those expectations into an editable, versioned contract.
3. **Gate** every new batch against the pinned contract. New data is never
   allowed to silently redefine what "good" means.

That separation is the whole product. A rule learned from the same batch it
checks is not a test; it is a mirror.

| Mode | Command | What you get |
|---|---|---|
| Explore | `dqdoctor check` without `--rules` | profile + **suggestions**; score is `n/a` |
| Pin | `dqdoctor rules-init` | a YAML/JSON contract you can review and commit |
| Gate | `dqdoctor check --rules` | pinned rules executed; nothing re-learned |
| Onboard | `dqdoctor baseline capture` | known failures exempted, without hiding new ones |

### Highlights

- **One command, full checkup** — profile, suggest, validate, score and render
  HTML in a single pass.
- **Trustworthy gate** — contract mode ignores `--sample-rows`, so a sampled
  count can never gate a batch.
- **Explicit statuses** — `pass`, `fail`, `skip`, `suggestion`, `error`; no
  inference from counters or empty tables.
- **Severity-weighted score** — `high=1.0`, `medium=0.5`, `low=0.25`; skipped,
  suggested and errored rules stay out of the denominator.
- **Real referential integrity** — DB-declared foreign keys (including
  composite and cross-schema keys) plus conservative name-based candidates.
- **PII triage** — emails, phone numbers, ID cards, bank cards, IPs and MACs;
  evidence-backed, with raw samples never written to reports.
- **Five export formats** — dbt `data_tests`, Great Expectations 1.x, SodaCL,
  Deequ, Markdown.
- **Schedulers and agents** — Airflow operator, shared `run_gate()`, and a
  stdio **MCP** server.
- **Three backends first-class** — DuckDB, PostgreSQL, MySQL; CSV, Parquet,
  JSON/JSONL and directories via DuckDB.
- **CI-native** — HTML / JSON / JUnit, deterministic exit codes, baseline
  exemptions, GitHub Actions workflow.

### Install

```bash
# Core (DuckDB + CLI)
pip install dq-doctor

# PostgreSQL / MySQL
pip install "dq-doctor[sql]"

# MCP server (Claude Desktop, Cursor, other MCP clients)
pip install "dq-doctor[mcp]"

# Read-only report server
pip install "dq-doctor[dashboard]"
```

Python **3.12+**. The `[sql]` extra installs SQLAlchemy, `psycopg[binary]`
(psycopg3) and PyMySQL. PostgreSQL URLs are normalized to
`postgresql+psycopg://`; MySQL URLs to `mysql+pymysql://`.

### 60-second quickstart

```bash
# 1. A demo database with intentional problems
dqdoctor demo --dirty --output dq-demo.duckdb

# 2. Profile + suggestions (nothing is verified yet)
dqdoctor check --db dq-demo.duckdb --all-tables --out explore.html

# 3. Pin a contract from a clean reference batch
dqdoctor rules-init --db dq-demo.duckdb --all-tables --out contract.yml

# 4. Gate a new batch against the pinned contract
dqdoctor check \
  --db dq-demo.duckdb --table dirty_orders \
  --rules contract.yml \
  --out report.html --json report.json --junit junit.xml \
  --ci --max-failures 0 --fail-on high
```

`rules-init` is meant for a **clean reference batch**. Point it at production
data only after you have reviewed what it learned.

### Commands

```bash
dqdoctor --version
dqdoctor doctor
dqdoctor init
dqdoctor demo [--dirty] [--force] [-o FILE]
dqdoctor tables --db SRC
dqdoctor profile --db SRC --table T [--sample-rows N] [--out profile.json]
dqdoctor check --db SRC [--table T | --all-tables] [--rules C]
dqdoctor rules-init --db SRC [--table T | --all-tables] --out C
dqdoctor baseline capture --db SRC --rules C --out baseline.json
dqdoctor migrate --in OLD.yml --out C
dqdoctor export --rules C --format dbt|gx|soda|deequ|markdown --out FILE
dqdoctor drift --old a.json --new b.json
dqdoctor mcp [--config .dqdoctor.yml]
dqdoctor serve --report report.json [--host 127.0.0.1] [--port 8501]
```

### The contract

```yaml
version: 1
datasource: dq-demo.duckdb

tables:
  dirty_orders:
    rules:
      - id: dirty_orders/not_null:order_id
        type: not_null
        column: order_id
        severity: high
        reason: order id is the business key

      - id: dirty_orders/unique:order_id
        type: unique
        column: order_id
        severity: high

      - id: dirty_orders/accepted_values:status
        type: accepted_values
        column: status
        params:
          values: [paid, shipped, refunded]
          null_policy: ignore

      - id: dirty_orders/range:total_amount
        type: range
        column: total_amount
        params: {min: '0.00', max: '500.00'}   # strings preserve precision
        severity: low
```

Rule ids are scoped to the table (`table/type:column`), so the same column
name can appear in several tables. Numeric boundaries are stored as strings
and restored as exact numerics at execution time.

#### Custom SQL rules

```yaml
- id: dirty_orders/sql:no_negative_amounts
  type: sql
  column: '*'
  severity: high
  params:
    query: "SELECT COUNT(*) FROM dirty_orders WHERE total_amount < 0"
    expect: {mode: eq, value: 0}
```

`expect` supports `eq`, `lte`, `gte` and `between`. A SQL rule must return
exactly one row and one column; multiple rows are an **error** (they are never
silently truncated to the first row). Sessions are read-only, statements are
single-statement `SELECT`/`WITH`, and a timeout applies.

### Rules

| Type | Applies to | What it verifies |
|---|---|---|
| `not_null` | any column | no NULLs |
| `unique` | any column | uniqueness over **non-NULL** values; NULLs belong to `not_null` |
| `accepted_values` | enum columns | every non-NULL value is in the set; `null_policy: ignore \| fail`; a NULL entry in `values` never makes an invalid value pass |
| `range` | numeric | `min` / `max` bounds |
| `freshness` | `TIMESTAMP` / `DATE` | newest value is within `max_age_hours`; future timestamps fail |
| `regex` | text | backend-native regex |
| `row_count` | table | `exact`, `min`, `max` |
| `cross_field` | two columns | `<`, `<=`, `>`, `>=`, `=`, `!=` |
| `sql` | operator query | scalar query + `expect` contract |

### Gate semantics

- `--fail-on high|medium|low` selects which failures participate.
- `--max-failures N` tolerates up to N participating failures.
- Referential integrity is checked on **every** run; a baseline only exempts
  specific known relationships, never turns the check off.
- A missing table named in the contract is an **execution error** with
  `--all-tables` (exit `2`), not a silent pass.
- File datasources (CSV/Parquet/JSON) cannot enforce the DuckDB engine-level
  file restriction, so enabled SQL rules on them are an **execution error**
  with a remediation message; use `regex`, `row_count`, `cross_field`,
  `range` or `accepted_values` instead.

### Baselines (v2)

```bash
# Capture the failures you knowingly accept
dqdoctor baseline capture --db prod --rules contract.yml --out baseline.json

# Gate new batches: known failures are exempted, new/deteriorating ones are not
dqdoctor check --db prod --all-tables --rules contract.yml \
  --baseline baseline.json --ci
```

Baseline v2 records the **rule definition hash** and the **orphan count** for
each known failure. Changing a rule, adding a new failure on the same rule,
or increasing orphan rows trips the gate again. Baselines created by v1.0.6
must be re-captured; `check` refuses a v1 baseline with a clear diagnostic.

### Data sources

```bash
# DuckDB file
dqdoctor check --db analytics.duckdb --all-tables

# DuckDB-readable files / directory
dqdoctor check --db exports/orders.parquet --rules contract.yml
dqdoctor check --db exports/2026-11/ --rules contract.yml

# PostgreSQL
export DQTEST_PG="postgresql://user:pass@host:5432/db"
dqdoctor check --db "$DQTEST_PG" --all-tables --rules contract.yml

# PostgreSQL non-default schema (sets search_path + metadata filter)
dqdoctor check --db "postgresql://user:pass@host/db?schema=analytics" ...

# MySQL (?schema= replaces the database segment)
dqdoctor check --db "mysql://user:pass@host/db?schema=analytics" ...
```

Connection timeout defaults to **10 seconds**. An explicit
`?connect_timeout=5` in the URL wins; `DQ_CONNECT_TIMEOUT=5` overrides the
default. Connection failures exit `2` with a redacted datasource.

Named aliases live in `.dqdoctor.yml`:

```yaml
datasources:
  demo: dq-demo.duckdb
  prod: postgresql://user:pass@host:5432/analytics?schema=public
default: demo
```

```bash
dqdoctor init
dqdoctor check --db prod --all-tables --rules contract.yml --ci
```

### Outputs

| Flag | Format | Notes |
|---|---|---|
| `--out report.html` | HTML | escaped; no raw samples; numeric/date ranges readable; text min/max fingerprinted |
| `--json report.json` | JSON | `schema_version`, `dqdoctor_version`, `score_version`; multi-table runs write one file per table |
| `--junit junit.xml` | JUnit XML | one testsuite per table; skipped/failed/error counts match elements |

The HTML/JSON reports never include raw sample values or connection passwords.
PII findings carry `matched_fraction` and `sample_size`, not the values.

### CI

```yaml
- name: Data quality gate
  run: |
    pip install "dq-doctor[sql]"
    dqdoctor check \
      --db "${{ secrets.DATABASE_URL }}" \
      --all-tables --rules contract.yml \
      --out report.html --json report.json --junit junit.xml \
      --baseline baseline.json --ci --fail-on high
```

- `0` — clean or within policy
- `1` — quality gate tripped
- `2` — input/config/connection/execution error (always, even without `--ci`)

The repository ships a GitHub Actions workflow with a Python 3.12–3.14 matrix,
SQL backend services, live-backend tests and a wheel build/install smoke test.

### Schedulers, MCP and exports

**Airflow**

```python
from dqdoctor.gate import DQDoctorOperator

check = DQDoctorOperator(
    task_id="dq_orders",
    source="prod",
    all_tables=True,
    rules_path="contract.yml",
    baseline_path="baseline.json",
    max_failures=0,
    fail_on="high",
    out="report.json",
)
```

`run_gate()` is the same entry point for cron/Prefect/custom workers:
`QualityGateError` = gate tripped, `RunnerError` = input/execution error.

**MCP**

```bash
pip install "dq-doctor[mcp]"
dqdoctor mcp --config .dqdoctor.yml
```

Tools: `list_datasets`, `profile_table`, `run_check`, `get_summary`. Datasource
names are resolved through the config aliases; callers cannot pass arbitrary
filesystem paths or URLs. The server is tested with the official MCP client
over stdio (SDK 1.x; SDK 2.x is not supported yet).

**Exports**

```bash
dqdoctor export --rules contract.yml --format dbt      --out schema.yml   # dbt >= 1.10.5
dqdoctor export --rules contract.yml --format gx       --out suite.json   # GX 1.x
dqdoctor export --rules contract.yml --format soda     --out checks.yml   # SodaCL
dqdoctor export --rules contract.yml --format deequ    --out checks.json  # pydeequ
dqdoctor export --rules contract.yml --format markdown --out dict.md
```

Unmappable rule types are emitted as comments / `meta.unmapped_rule_ids`, never
silently dropped.

### Security model

1. **Engine layer (authoritative for DuckDB files).** DuckDB datasources open
   with `enable_external_access=false`. `query_table`, `glob`, replacement
   scans and `read_*` fail with `PermissionException` even if the SQL policy is
   bypassed.
2. **SQL policy (all backends).** Single-statement `SELECT`/`WITH`; write
   keywords (including data-modifying CTEs) rejected; file/network readers
   (`read_*`, `parquet_metadata`, `pg_read_file`, `LOAD_FILE`, …) rejected;
   `FROM`/`JOIN` literal table sources rejected; executable comments and
   `INTO OUTFILE`/`INTO DUMPFILE` rejected.
3. **Read-only sessions.** PostgreSQL `default_transaction_read_only`; MySQL
   `SET SESSION TRANSACTION READ ONLY` (the engine enforces it on the check
   path); DuckDB files are opened read-only.
4. **Credentials and samples.** Userinfo passwords and query secrets
   (`?password=`, `?token=`, …) are masked in reports, logs and persisted
   contracts. URL contracts store the redacted form; pass the real URL with
   `--db` or an alias. `.gitignore` covers `contract.yml` and `*.duckdb.bak`.
5. **Sampling.** `--sample-rows` is an **explore/profile-only** convenience.
   Contract mode always profiles the full table; a sampled count can never
   gate a batch.

### Architecture

```
dqdoctor/
  cli.py          parameters + rendering; execution lives in the engine
  engine.py       CheckEngine.run: one connection, FK plan once, per-table
                  profile -> rules -> score; decide_exit() is the single
                  exit-code decision point
  contract.py     versioned contract (v1), migration, table-scoped rule ids
  profiling.py    batched aggregates (2–3 queries per table, not per column)
  rulecheck.py    built-in rules; reuses profile aggregates for zero-extra
                  queries where possible
  sqlrules.py     guarded operator SQL (sqlpolicy + sqlexec)
  scoring.py      severity-weighted score; no executed rules -> None
  baseline.py     v2 known-failure exemptions (definition hash + counts)
  datasources.py  URL/path/alias resolution, read-only sessions, timeouts
  fkdeclared.py   DB-declared FKs (composite, cross-schema)
  fkcheck.py      FK plan + orphan counting (each relationship once)
  outputs.py      HTML / JSON / JUnit (redacted)
  gate.py         run_gate + Airflow operator (explicit execute)
  mcp_server.py   stdio MCP tools, shared engine
  exporters/      dbt / GX / Soda / Deequ / Markdown
```

### Performance

Profiling is batched: one aggregate per table plus a small number of extras.
On the reference benchmark:

- 40 integer columns: **2 queries**
- 1,000,000 rows × 4 columns: **3 queries**
- text columns cost one extra `DISTINCT ... LIMIT` each (PII evidence); this is
  documented and visible, not hidden.

### Compatibility and verification

- Python 3.12, 3.13 and 3.14 in the CI matrix; 3.12 is the primary local version.
- DuckDB 1.x, PostgreSQL 16.2, MySQL 9.5 tested with real servers.
- dbt `data_tests` with nested `arguments` (dbt >= 1.10.5), Great Expectations
  1.x suite shape, SodaCL, Deequ and Markdown exports.
- `216` tests passed, `11` skipped in the local environment (optional
  backend/dashboard extras absent); Ruff clean.
- MCP stdio round-trip tested with the official client (SDK 1.x).

Known limits: heuristic FKs are name-based candidates (declared keys always
win); `freshness` treats naive timestamps as local wall-clock time; PII
detection is a triage aid, not a compliance tool; SQL rules are not supported
on file datasources; CI is the final gate and should be run on your fork.

### AI agent install prompt

Copy this block to an AI coding agent:

```text
Install and validate dq-doctor in a local sandbox. Do not touch production data.

1. Verify Python >= 3.12. Install: pip install "dq-doctor[sql,mcp]".
2. Run: dqdoctor --version && dqdoctor doctor. Stop if doctor exits 2.
3. Smoke test in a temp directory:
   dqdoctor demo --dirty --output dq-demo.duckdb
   dqdoctor rules-init --db dq-demo.duckdb --all-tables --out contract.yml
   dqdoctor check --db dq-demo.duckdb --table dirty_orders \
     --rules contract.yml --out report.html --json report.json --ci
   The dirty demo is expected to exit 1. Report the failing rule ids and the
   report.html / report.json paths.
4. For a real datasource: use --db or a named alias from .dqdoctor.yml. Never
   echo credentials. Explore first (check without --rules), then rules-init on
   a clean reference batch, then check --rules --baseline baseline.json --ci.
5. If exit code is 2, show the exact diagnostic and stop; do not retry with
   guessed credentials or file paths.
6. Final report: version, Python, backend, commands run, exit codes, failed
   rules, artifacts produced.
```

### Development

```bash
git clone https://github.com/pugyy/dq-doctor
cd dq-doctor
pip install -e ".[dev,sql,dashboard,mcp]"
pytest tests/ -q
ruff check dqdoctor/ tests/
```

Live backend tests:

```bash
DQTEST_PG="postgresql://user:pass@host:5432/db" \
DQTEST_MYSQL="mysql://user:pass@host:3306/db" \
DQTEST_MYSQL_ADMIN="mysql://root:pass@host:3306/mysql" \
DQ_LIVE_REQUIRED=1 pytest tests/test_backends.py tests/test_live_backends.py -v
```

Documentation: [migration 0.7 → 1.0](https://github.com/pugyy/dq-doctor/blob/main/docs/migration-1.0.md) ·
[configuration](https://github.com/pugyy/dq-doctor/blob/main/docs/config.md) ·
[custom SQL](https://github.com/pugyy/dq-doctor/blob/main/docs/custom-sql-rules.md) ·
[exporters](https://github.com/pugyy/dq-doctor/blob/main/docs/exporters.md) ·
[PostgreSQL/MySQL](https://github.com/pugyy/dq-doctor/blob/main/docs/postgres-mysql.md) ·
[architecture](https://github.com/pugyy/dq-doctor/blob/main/docs/architecture.md) ·
[limitations](https://github.com/pugyy/dq-doctor/blob/main/docs/limitations.md) ·
[changelog](https://github.com/pugyy/dq-doctor/blob/main/CHANGELOG.md).

### License

MIT.

---

<a id="简体中文"></a>
## 简体中文

### 为什么是 dq-doctor

大多数数据质量工具要求你先写规则，再拿数据去碰。dq-doctor 反过来：

1. **体检**：先分析表结构和数据形态（类型、空值、基数、范围、枚举、时间新鲜度、PII 线索）。
2. **定契约**：把这一批数据里学到的期望固定成可编辑、可提交的版本化契约。
3. **设门禁**：之后每一批新数据都按同一份契约检查，新数据不能悄悄把"合格"的定义改掉。

这个分离就是产品的全部。用同一批数据学规则、再用同一批数据验证，不叫测试，叫照镜子。

| 模式 | 命令 | 你会得到 |
|---|---|---|
| 探索 | `dqdoctor check`（不带 `--rules`） | 体检结果 + **建议**；分数为 `n/a` |
| 固化 | `dqdoctor rules-init` | 可审阅、可提交的 YAML/JSON 契约 |
| 门禁 | `dqdoctor check --rules` | 执行固定契约，绝不重新学习 |
| 存量接入 | `dqdoctor baseline capture` | 豁免已知失败，但不放过新增/恶化 |

### 核心特性

- **一行命令完整体检**：分析、建议、校验、评分、HTML 报告一次完成。
- **可信门禁**：契约模式忽略 `--sample-rows`，采样结果永远不能决定门禁。
- **显式状态**：`pass` / `fail` / `skip` / `suggestion` / `error`，不靠计数器猜。
- **按严重级加权评分**：`high=1.0`、`medium=0.5`、`low=0.25`；跳过/建议/错误不计入分母。
- **真正的参照完整性**：数据库声明外键（含组合键、跨 schema）优先，辅以保守的命名候选。
- **PII 初筛**：邮箱、手机号、身份证、银行卡、IP、MAC；带证据比例，报告不落原始样本。
- **五种导出**：dbt `data_tests`、Great Expectations 1.x、SodaCL、Deequ、Markdown。
- **调度与 Agent**：Airflow Operator、共享 `run_gate()`、stdio **MCP** server。
- **三种后端一等支持**：DuckDB、PostgreSQL、MySQL；CSV / Parquet / JSON / 目录走 DuckDB。
- **CI 原生**：HTML / JSON / JUnit、确定退出码、基线豁免、GitHub Actions workflow。

### 安装

```bash
# 核心（DuckDB + CLI）
pip install dq-doctor

# PostgreSQL / MySQL
pip install "dq-doctor[sql]"

# MCP server（Claude Desktop、Cursor 等）
pip install "dq-doctor[mcp]"

# 只读报告服务
pip install "dq-doctor[dashboard]"
```

需要 Python **3.12+**。`[sql]` 会安装 SQLAlchemy、`psycopg[binary]`（psycopg3）和 PyMySQL。PostgreSQL URL 会归一化为 `postgresql+psycopg://`，MySQL URL 归一化为 `mysql+pymysql://`。

### 60 秒上手

```bash
# 1. 生成带脏数据的演示库
dqdoctor demo --dirty --output dq-demo.duckdb

# 2. 体检 + 建议（还没有任何规则被验证）
dqdoctor check --db dq-demo.duckdb --all-tables --out explore.html

# 3. 从干净参考批次固化契约
dqdoctor rules-init --db dq-demo.duckdb --all-tables --out contract.yml

# 4. 用同一份契约门禁新批次
dqdoctor check \
  --db dq-demo.duckdb --table dirty_orders \
  --rules contract.yml \
  --out report.html --json report.json --junit junit.xml \
  --ci --max-failures 0 --fail-on high
```

`rules-init` 应该指向**干净参考批次**。不要把生产脏数据直接拿来生成契约。

### 命令

```bash
dqdoctor --version
dqdoctor doctor
dqdoctor init
dqdoctor demo [--dirty] [--force] [-o FILE]
dqdoctor tables --db SRC
dqdoctor profile --db SRC --table T [--sample-rows N] [--out profile.json]
dqdoctor check --db SRC [--table T | --all-tables] [--rules C]
dqdoctor rules-init --db SRC [--table T | --all-tables] --out C
dqdoctor baseline capture --db SRC --rules C --out baseline.json
dqdoctor migrate --in OLD.yml --out C
dqdoctor export --rules C --format dbt|gx|soda|deequ|markdown --out FILE
dqdoctor drift --old a.json --new b.json
dqdoctor mcp [--config .dqdoctor.yml]
dqdoctor serve --report report.json [--host 127.0.0.1] [--port 8501]
```

### 契约

```yaml
version: 1
datasource: dq-demo.duckdb

tables:
  dirty_orders:
    rules:
      - id: dirty_orders/not_null:order_id
        type: not_null
        column: order_id
        severity: high
        reason: order id is the business key

      - id: dirty_orders/unique:order_id
        type: unique
        column: order_id
        severity: high

      - id: dirty_orders/accepted_values:status
        type: accepted_values
        column: status
        params:
          values: [paid, shipped, refunded]
          null_policy: ignore

      - id: dirty_orders/range:total_amount
        type: range
        column: total_amount
        params: {min: '0.00', max: '500.00'}   # 字符串保精度
        severity: low
```

规则 id 带表作用域（`表/类型:列`），不同表可以出现同名列。数值边界以字符串保存，执行时还原为精确数值。

#### 自定义 SQL 规则

```yaml
- id: dirty_orders/sql:no_negative_amounts
  type: sql
  column: '*'
  severity: high
  params:
    query: "SELECT COUNT(*) FROM dirty_orders WHERE total_amount < 0"
    expect: {mode: eq, value: 0}
```

`expect` 支持 `eq`、`lte`、`gte`、`between`。SQL 规则必须返回**恰好一行一列**；多行会报执行错误，绝不悄悄取第一行。会话只读、单语句 `SELECT`/`WITH`、带超时。

### 规则

| 类型 | 适用 | 校验内容 |
|---|---|---|
| `not_null` | 任意列 | 无 NULL |
| `unique` | 任意列 | 非 NULL 值唯一；NULL 归 `not_null` 管 |
| `accepted_values` | 枚举列 | 非 NULL 值都在集合内；`null_policy: ignore \| fail`；集合里写 NULL 不会放过非法值 |
| `range` | 数值列 | `min` / `max` 边界 |
| `freshness` | `TIMESTAMP` / `DATE` | 最新值在 `max_age_hours` 内；未来时间判失败 |
| `regex` | 文本列 | 后端原生正则 |
| `row_count` | 表 | `exact` / `min` / `max` |
| `cross_field` | 两列 | `<`、`<=`、`>`、`>=`、`=`、`!=` |
| `sql` | 操作者查询 | 标量查询 + `expect` 契约 |

### 门禁语义

- `--fail-on high|medium|low` 决定哪些失败参与门禁。
- `--max-failures N` 容忍 N 个参与失败。
- 参照完整性**每次都检查**；baseline 只豁免具体的已知关系，不会把检查关掉。
- `--all-tables` 下，契约里点名但数据库里不存在的表是**执行错误**（退出 `2`），不是静默通过。
- 文件源（CSV/Parquet/JSON）无法使用 DuckDB 引擎级文件限制，因此文件源上已启用的 SQL 规则会报**执行错误**并给出整改提示；请改用 `regex`、`row_count`、`cross_field`、`range` 或 `accepted_values`。

### 基线（v2）

```bash
# 记录你明知接受的历史失败
dqdoctor baseline capture --db prod --rules contract.yml --out baseline.json

# 门禁新批次：已知失败豁免，新增/恶化不豁免
dqdoctor check --db prod --all-tables --rules contract.yml \
  --baseline baseline.json --ci
```

基线 v2 记录**规则定义哈希**和**孤儿计数**。改规则、同一规则新增失败、孤儿数增加，都会重新触发门禁。v1.0.6 及更早生成的 v1 基线必须重新 capture；`check` 会明确拒绝 v1 基线。

### 数据源

```bash
# DuckDB 文件
dqdoctor check --db analytics.duckdb --all-tables

# DuckDB 可读文件 / 目录
dqdoctor check --db exports/orders.parquet --rules contract.yml
dqdoctor check --db exports/2026-11/ --rules contract.yml

# PostgreSQL
dqdoctor check --db "postgresql://user:pass@host:5432/db" --all-tables --rules contract.yml

# PostgreSQL 非默认 schema（设置 search_path + 元数据过滤）
dqdoctor check --db "postgresql://user:pass@host/db?schema=analytics" ...

# MySQL（?schema= 替换 URL 里的数据库段）
dqdoctor check --db "mysql://user:pass@host/db?schema=analytics" ...
```

连接超时默认 **10 秒**。URL 显式 `?connect_timeout=5` 优先；`DQ_CONNECT_TIMEOUT=5` 覆盖默认值。连接失败退出 `2`，报告中的连接串已脱敏。

命名别名放在 `.dqdoctor.yml`：

```yaml
datasources:
  demo: dq-demo.duckdb
  prod: postgresql://user:pass@host:5432/analytics?schema=public
default: demo
```

```bash
dqdoctor init
dqdoctor check --db prod --all-tables --rules contract.yml --ci
```

### 输出

| 参数 | 格式 | 说明 |
|---|---|---|
| `--out report.html` | HTML | 转义；无原始样本；数值/日期范围可读；文本 min/max 指纹化 |
| `--json report.json` | JSON | 带 `schema_version`、`dqdoctor_version`、`score_version`；多表时每表一份 |
| `--junit junit.xml` | JUnit XML | 每表一个 testsuite；skipped/failed/error 计数与元素一致 |

HTML/JSON 不包含原始样本值或连接密码。PII 发现只带 `matched_fraction` 和 `sample_size`，不带原始值。

### CI

```yaml
- name: Data quality gate
  run: |
    pip install "dq-doctor[sql]"
    dqdoctor check \
      --db "${{ secrets.DATABASE_URL }}" \
      --all-tables --rules contract.yml \
      --out report.html --json report.json --junit junit.xml \
      --baseline baseline.json --ci --fail-on high
```

- `0`：干净或在策略内
- `1`：质量门禁触发
- `2`：输入/配置/连接/执行错误（无论有没有 `--ci`）

仓库自带 GitHub Actions workflow：Python 3.12–3.14 矩阵、SQL 后端服务、真实后端测试、wheel 构建安装冒烟。

### 调度、MCP 与导出

**Airflow**

```python
from dqdoctor.gate import DQDoctorOperator

check = DQDoctorOperator(
    task_id="dq_orders",
    source="prod",
    all_tables=True,
    rules_path="contract.yml",
    baseline_path="baseline.json",
    max_failures=0,
    fail_on="high",
    out="report.json",
)
```

`run_gate()` 是 cron / Prefect / 自研 worker 的同一入口：`QualityGateError` 表示门禁触发，`RunnerError` 表示输入/执行错误。

**MCP**

```bash
pip install "dq-doctor[mcp]"
dqdoctor mcp --config .dqdoctor.yml
```

工具：`list_datasets`、`profile_table`、`run_check`、`get_summary`。数据源只能通过配置别名解析，调用方不能传任意文件路径或 URL。stdio 往返用官方 MCP 客户端测过（SDK 1.x；暂不支持 2.x）。

**导出**

```bash
dqdoctor export --rules contract.yml --format dbt      --out schema.yml   # dbt >= 1.10.5
dqdoctor export --rules contract.yml --format gx       --out suite.json   # GX 1.x
dqdoctor export --rules contract.yml --format soda     --out checks.yml   # SodaCL
dqdoctor export --rules contract.yml --format deequ    --out checks.json  # pydeequ
dqdoctor export --rules contract.yml --format markdown --out dict.md
```

无法映射的规则会写成注释 / `meta.unmapped_rule_ids`，不会被静默丢弃。

### 安全模型

1. **引擎层（DuckDB 文件权威）**：DuckDB 数据源以 `enable_external_access=false` 打开；即使策略被绕过，`query_table`、`glob`、replacement scan、`read_*` 也会 `PermissionException`。
2. **SQL 策略（全后端）**：单语句 `SELECT`/`WITH`；写关键字（含 DML CTE）拒绝；文件/网络读函数（`read_*`、`parquet_metadata`、`pg_read_file`、`LOAD_FILE` 等）拒绝；`FROM`/`JOIN` 字面量表源拒绝；可执行注释、`INTO OUTFILE`/`INTO DUMPFILE` 拒绝。
3. **只读会话**：PostgreSQL `default_transaction_read_only`；MySQL `SET SESSION TRANSACTION READ ONLY`（check 路径由引擎再次 enforce）；DuckDB 文件只读打开。
4. **凭据与样本**：userinfo 密码、query 秘密键（`?password=`、`?token=` 等）在报告/日志/持久化契约中全部掩码；URL 契约存脱敏形式，真实 URL 用 `--db` 或别名传入；`.gitignore` 覆盖 `contract.yml` 和 `*.duckdb.bak`。
5. **采样**：`--sample-rows` 只服务 explore/profile；契约模式恒全表，采样结果不可能决定门禁。

### 架构

```
dqdoctor/
  cli.py          参数与渲染；执行下沉引擎
  engine.py       CheckEngine.run：单连接、FK 计划一次、逐表 profile→规则→评分；
                  decide_exit() 是唯一退出码判定点
  contract.py     版本化契约（v1）、迁移、表作用域规则 id
  profiling.py    批量聚合（每表 2–3 条查询，不随列宽线性增长）
  rulecheck.py    内置规则；复用 profile 聚合，能零额外查询就零额外查询
  sqlrules.py     受守卫的操作者 SQL（sqlpolicy + sqlexec）
  scoring.py      严重级加权评分；无已执行规则 → None
  baseline.py     v2 已知失败豁免（定义哈希 + 计数）
  datasources.py  URL/路径/别名解析、只读会话、连接超时
  fkdeclared.py   数据库声明外键（组合、跨 schema）
  fkcheck.py      FK 计划 + 孤儿计数（每条关系只算一次）
  outputs.py      HTML / JSON / JUnit（脱敏）
  gate.py         run_gate + Airflow operator（显式 execute）
  mcp_server.py   stdio MCP 工具，复用引擎
  exporters/      dbt / GX / Soda / Deequ / Markdown
```

### 性能

体检是批量的：每张表一条聚合，加少量额外查询。参考基准：

- 40 个整数列：**2 条查询**
- 100 万行 × 4 列：**3 条查询**
- 文本列每列额外一条 `DISTINCT ... LIMIT`（PII 证据）；这是显式成本，不藏着。

### 兼容性与验证

- CI 矩阵覆盖 Python 3.12、3.13、3.14；本地主版本 3.12。
- DuckDB 1.x、PostgreSQL 16.2、MySQL 9.5 用真实服务测过。
- dbt `data_tests` + 嵌套 `arguments`（dbt >= 1.10.5）、Great Expectations 1.x、SodaCL、Deequ、Markdown 导出。
- 本地 **216** 通过、**11** 跳过（缺可选后端/面板 extras）；Ruff 全绿。
- MCP stdio 往返用官方客户端测过（SDK 1.x）。

已知边界：启发式 FK 是基于命名的候选（声明外键优先）；`freshness` 把无时区时间当作本地墙上时间；PII 检测是初筛不是合规工具；文件源不支持 SQL 规则；CI 是最终门禁，建议在你的 fork 上跑一次。

### AI Agent 安装提示词

把下面这段直接复制给 AI Agent：

```text
在本地沙箱安装并验证 dq-doctor，不要触碰生产数据。

1. 确认 Python >= 3.12，安装：pip install "dq-doctor[sql,mcp]"。
2. 运行：dqdoctor --version && dqdoctor doctor。doctor 退出 2 就停止。
3. 在临时目录做冒烟：
   dqdoctor demo --dirty --output dq-demo.duckdb
   dqdoctor rules-init --db dq-demo.duckdb --all-tables --out contract.yml
   dqdoctor check --db dq-demo.duckdb --table dirty_orders \
     --rules contract.yml --out report.html --json report.json --ci
   脏演示库预期退出 1；报告失败的规则 id 和 report.html / report.json 路径。
4. 接真实数据源时：用 --db 或 .dqdoctor.yml 里的别名；不要回显凭据。先探索
   （check 不带 --rules），再在干净参考批次上 rules-init，最后
   check --rules --baseline baseline.json --ci。
5. 退出码 2：原样展示诊断并停止；不要用猜的凭据或路径重试。
6. 最终汇报：版本、Python、后端、执行的命令、退出码、失败规则、产物路径。
```

### 开发

```bash
git clone https://github.com/pugyy/dq-doctor
cd dq-doctor
pip install -e ".[dev,sql,dashboard,mcp]"
pytest tests/ -q
ruff check dqdoctor/ tests/
```

真实后端测试：

```bash
DQTEST_PG="postgresql://user:pass@host:5432/db" \
DQTEST_MYSQL="mysql://user:pass@host:3306/db" \
DQTEST_MYSQL_ADMIN="mysql://root:pass@host:3306/mysql" \
DQ_LIVE_REQUIRED=1 pytest tests/test_backends.py tests/test_live_backends.py -v
```

文档：[0.7 → 1.0 迁移](https://github.com/pugyy/dq-doctor/blob/main/docs/migration-1.0.md) ·
[配置](https://github.com/pugyy/dq-doctor/blob/main/docs/config.md) ·
[自定义 SQL](https://github.com/pugyy/dq-doctor/blob/main/docs/custom-sql-rules.md) ·
[导出](https://github.com/pugyy/dq-doctor/blob/main/docs/exporters.md) ·
[PostgreSQL/MySQL](https://github.com/pugyy/dq-doctor/blob/main/docs/postgres-mysql.md) ·
[架构](https://github.com/pugyy/dq-doctor/blob/main/docs/architecture.md) ·
[限制](https://github.com/pugyy/dq-doctor/blob/main/docs/limitations.md) ·
[更新记录](https://github.com/pugyy/dq-doctor/blob/main/CHANGELOG.md)。

### 许可证

MIT。
