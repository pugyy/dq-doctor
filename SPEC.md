# dq-doctor SPEC

## 项目目标

dq-doctor 是一个轻量级数据质量体检 CLI 工具。用户不需要手写 YAML，不需要记 Great Expectations 或 dbt 的规则语法，只需要一行命令，就能对数据库表做 profiling、自动生成质量检查规则、执行校验并输出 HTML 报告。

## 非目标（第一版不做）

- 不依赖 LLM API
- 不接 Spark / Flink / Kafka / Airflow
- 不做 Web UI
- 不做实时数据质量监控
- 不替代 Great Expectations / Soda / dbt，而是它们之前的快速体检层

## MVP 功能边界

| 功能 | 包含 | 不包含 |
|------|------|--------|
| 数据库支持 | DuckDB | PostgreSQL / MySQL（后续扩展） |
| Profiling | 字段统计、语义推断 | 跨表关联分析 |
| 规则类型 | not_null / unique / accepted_values / range / freshness | 自定义正则 / 跨表一致性 |
| 输出格式 | HTML 报告 + JSON profile | dbt schema.yml / GX suite（后续扩展） |
| CLI 命令 | demo / profile / check | validate（单独）/ docs / watch |

## CLI 命令设计

```
dqdoctor demo
  -> 生成 examples/ecommerce/demo.duckdb 示例数据库

dqdoctor profile --db <path> --table <name> [--out profile.json]
  -> 输出表结构和字段统计信息

dqdoctor check --db <path> --table <name> [--out report.html]
  -> 自动 profile，生成规则，执行检查，输出 HTML 报告
```

## 核心数据结构设计

### ColumnProfile
```python
class ColumnProfile(BaseModel):
    name: str
    dtype: str
    null_count: int
    null_rate: float
    distinct_count: int
    distinct_rate: float
    min_value: Any
    max_value: Any
    sample_values: list[Any]
    inferred_semantic_type: str  # identifier / measure / category / timestamp / unknown
```

### TableProfile
```python
class TableProfile(BaseModel):
    table_name: str
    row_count: int
    columns: list[ColumnProfile]
```

### ProfileResult
```python
class ProfileResult(BaseModel):
    db_path: str
    table_name: str
    row_count: int
    columns: list[ColumnProfile]
    profiled_at: str  # ISO timestamp
```

### RuleSuggestion
```python
class RuleSuggestion(BaseModel):
    rule_id: str
    rule_type: str  # not_null / unique / accepted_values / range / freshness
    column: str
    params: dict[str, Any]
    confidence: float  # 0.0 ~ 1.0
    severity: str  # high / medium / low
    reason: str
    source: str  # heuristic / llm（后续）
```

### ValidationResult
```python
class ValidationResult(BaseModel):
    rule_id: str
    rule_type: str
    column: str
    passed: bool
    failed_count: int
    total_count: int
    message: str
```

### ReportResult
```python
class ReportResult(BaseModel):
    db_path: str
    table_name: str
    row_count: int
    column_count: int
    total_rules: int
    passed_rules: int
    failed_rules: int
    profile: ProfileResult
    rules: list[RuleSuggestion]
    results: list[ValidationResult]
    generated_at: str  # ISO timestamp
```

## 模块划分

```
dqdoctor/
  cli.py          命令行入口（Typer）
  models.py       Pydantic 数据结构
  demo.py         生成 DuckDB 示例数据库
  profiler.py     统计字段分布 + 语义推断
  rule_engine.py  根据 profile 生成质量规则
  validator.py    执行质量检查
  reporter.py     输出 HTML 报告
  connectors/
    duckdb.py     DuckDB 连接封装
```

## 规则引擎设计

所有规则为确定性启发式规则，不依赖 LLM。

### not_null
- 条件：`null_rate == 0` 或 `inferred_semantic_type == "identifier"`
- confidence：null_rate == 0 时 0.9，identifier 时 0.8
- severity：high（identifier）/ medium（其他）

### unique
- 条件：`inferred_semantic_type == "identifier"` 且 `distinct_rate >= 0.98`
- confidence：0.85
- severity：high

### accepted_values
- 条件：`inferred_semantic_type == "category"` 且 `distinct_count <= 20`
- params.values = sample_values
- confidence：0.8
- severity：medium

### range
- 条件：字段为数值类型（INT / BIGINT / FLOAT / DOUBLE / DECIMAL）
- params.min = min_value, params.max = max_value
- confidence：0.7
- severity：low

### freshness
- 条件：`inferred_semantic_type == "timestamp"`
- params.max_age_hours = 24（默认）
- confidence：0.75
- severity：high

## HTML 报告内容

报告包含以下区域：
1. **头部摘要**：表名、行数、字段数、检查规则数、通过/失败数、通过率
2. **字段 Profile 表格**：每个字段的类型、空值率、唯一率、min/max、语义类型
3. **规则建议表格**：规则类型、字段、confidence、severity、reason
4. **校验结果表格**：通过/失败、失败数、总数、message
5. **底部元信息**：生成时间、数据库路径

样式要求：纯 HTML + 内联 CSS，深色表头 + 斑马纹行，适合截图。

## 测试计划

| 测试文件 | 覆盖范围 |
|----------|----------|
| test_models.py | 模型创建、序列化、默认值 |
| test_demo.py | demo 数据库生成、表存在性、行数 |
| test_profiler.py | 字段统计准确性、语义推断 |
| test_rule_engine.py | 每种规则触发条件、reason 生成 |
| test_validator.py | 各类规则的通过/失败判定 |
| test_reporter.py | HTML 生成、包含关键内容 |
| test_cli.py | CLI 命令可运行、参数解析 |

测试使用 demo 数据库作为 fixture。

## 8 周 Roadmap

| 周次 | 目标 |
|------|------|
| 第 1 周 | SPEC + 项目骨架 + models.py + demo.py |
| 第 2 周 | profiler.py + profiler 测试 |
| 第 3 周 | rule_engine.py + rule_engine 测试 |
| 第 4 周 | validator.py + validator 测试 |
| 第 5 周 | reporter.py + HTML 报告 + reporter 测试 |
| 第 6 周 | CLI 整合 + 端到端测试 + README + 截图 |
| 第 7 周 | CI / pyproject 完善 / 文档 / 发布准备 |
| 第 8 周 | PostgreSQL 支持 / dbt schema.yml 导出 / 推广 |

## 技术栈

- Python 3.9+
- Typer：CLI
- DuckDB：数据库
- Pydantic：数据结构
- Jinja2：HTML 报告模板
- Rich：终端美化输出
- pytest：测试
- ruff：格式检查
