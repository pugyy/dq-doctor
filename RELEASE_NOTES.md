# dq-doctor v1.0.7

<p align="center">
  <a href="#english">English</a> · <a href="#简体中文">简体中文</a>
</p>

<a id="english"></a>
## English

**One command to profile data, pin a quality contract, and gate every new batch.**

This release closes the last false-pass paths found by the external audit and
makes the exported artifacts load in the real tools they target.

### Highlights

- **No silent gate passes**
  - `accepted_values` no longer treats a `NULL` whitelist entry as a wildcard.
  - SQL rules returning zero, multiple rows or multiple columns are execution
    errors, not "first row wins".
  - `check --all-tables --rules` reports contract tables missing from the
    database as exit `2` instead of skipping them.
  - Enabled SQL rules on file datasources return an execution error with a
    remediation message instead of a harmless-looking `SKIP`.
- **Referential integrity and baselines**
  - PostgreSQL composite and cross-schema foreign keys preserve column order
    and target schema; orphan counting follows the qualified target.
  - Baseline **v2** hashes each rule definition and records orphan counts, so
    a changed rule or a growing orphan set re-trips the gate.
  - `baseline capture` refuses runs with execution errors.
  - **Breaking:** v1 baselines must be re-captured.
- **Connections and credentials**
  - SQL backends default to a **10s** connect timeout. Precedence:
    `?connect_timeout=` in the URL → `DQ_CONNECT_TIMEOUT` → 10s. Invalid
    values are a configuration error.
  - Connection failures exit `2` with a redacted datasource.
  - `dqdoctor migrate` redacts credentials in legacy `db:` URLs.
- **MCP and exports**
  - MCP SDK is pinned to `mcp>=1.12,<2`; the stdio server is tested with the
    official client, uses registered aliases and honors table selection.
  - dbt export targets dbt >= 1.10.5 `data_tests` with nested `arguments`;
    range expressions no longer repeat the column name.
  - Great Expectations suites load through the GX 1.x constructor; exact row
    counts map to `expect_table_row_count_to_equal`.
  - SodaCL, Deequ and Markdown exports remain covered.

### Verification

- `231` tests passed, `~84.7%` statement coverage, Ruff clean.
- Real PostgreSQL 16.2 and MySQL 9.5: `8/8` cross-backend + `6/6` live cases,
  including the second-database MySQL `?schema=` path.
- CI matrix: Python 3.12, 3.13, 3.14.
- Real toolchain checks: dbt (19 checks), SodaCL (21 checks), GX 1.25 suite
  load/registration.
- Wheel/sdist rebuilt from the fixed tree; clean-venv install smoke-tested.

### Breaking changes

1. **Baseline v2** — re-run `dqdoctor baseline capture`.
2. **File-datasource SQL rules now fail** (disable them or use
   `regex`/`row_count`/`cross_field`/`range`/`accepted_values`).
3. **PostgreSQL URLs** normalize to `postgresql+psycopg://`; `[sql]` installs
   psycopg3.
4. **MySQL `?schema=`** replaces the database segment.
5. **dbt export** requires dbt >= 1.10.5.

### Install

```bash
pip install -U "dq-doctor[sql,mcp,dashboard]"
dqdoctor doctor
```

Full documentation, bilingual README, contract examples and the copy-paste AI
agent install prompt:
<https://github.com/pugyy/dq-doctor#readme>

---

<a id="简体中文"></a>
## 简体中文

**一行命令完成数据体检、固化质量契约，并对每一批新数据设门禁。**

本版关闭了外部审计发现的最后几条"误过"路径，并让导出的制品能被真实工具加载。

### 重点

- **不再静默误过**
  - `accepted_values` 的白名单里写 `NULL` 不再被当作通配符。
  - 自定义 SQL 返回 0 行、多行或多列都算执行错误，不再"取第一行"。
  - `check --all-tables --rules` 会把契约里点名、数据库里已消失的表报成退出码 `2`。
  - 文件源上已启用的 SQL 规则返回执行错误和整改提示，而不是看起来无害的 `SKIP`。
- **外键与基线**
  - PostgreSQL 组合外键、跨 schema 外键保留列顺序和目标 schema；孤儿计数按限定后的目标表执行。
  - 基线 **v2** 记录规则定义哈希和孤儿计数；改规则或孤儿增加都会重新触发门禁。
  - `baseline capture` 拒绝带执行错误的运行。
  - **破坏性变更**：v1 基线必须重新 capture。
- **连接与凭据**
  - SQL 后端默认 **10 秒**连接超时。优先级：URL 的 `?connect_timeout=` → `DQ_CONNECT_TIMEOUT` → 10 秒；非法值按配置错误处理。
  - 连接失败退出 `2`，报告中的连接串已脱敏。
  - `dqdoctor migrate` 会遮蔽旧 `db:` URL 里的凭据。
- **MCP 与导出**
  - MCP 约束到 `mcp>=1.12,<2`；stdio server 用官方客户端测过，只认注册别名并支持表选择。
  - dbt 导出面向 dbt >= 1.10.5 的 `data_tests` + 嵌套 `arguments`；range 表达式不再重复列名。
  - Great Expectations 套件可直接用 GX 1.x 构造器加载；精确行数映射到 `expect_table_row_count_to_equal`。
  - SodaCL、Deequ、Markdown 导出持续覆盖。

### 复验

- **231** 个测试通过，约 **84.7%** 语句覆盖率，Ruff 全绿。
- 真实 PostgreSQL 16.2 与 MySQL 9.5：跨后端 `8/8` + live `6/6`，含 MySQL 第二库 `?schema=` 路径。
- CI 矩阵：Python 3.12、3.13、3.14。
- 真实工具链：dbt 19 项、SodaCL 21 项、GX 1.25 套件加载/注册。
- 从修复后的源码重建 wheel/sdist，并在干净 venv 做安装冒烟。

### 破坏性变更

1. **基线 v2**：重新执行 `dqdoctor baseline capture`。
2. **文件源 SQL 规则现在会失败**：禁用，或改用 `regex`/`row_count`/`cross_field`/`range`/`accepted_values`。
3. **PostgreSQL URL** 归一化为 `postgresql+psycopg://`；`[sql]` 安装 psycopg3。
4. **MySQL `?schema=`** 替换 URL 里的数据库段，不再追加。
5. **dbt 导出**要求 dbt >= 1.10.5。

### 安装

```bash
pip install -U "dq-doctor[sql,mcp,dashboard]"
dqdoctor doctor
```

完整双语文档、契约示例、可复制给 AI Agent 的安装提示词：
<https://github.com/pugyy/dq-doctor#readme>
