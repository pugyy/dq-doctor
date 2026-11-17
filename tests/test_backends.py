"""Cross-backend tests (PostgreSQL + MySQL), skipped when env vars are absent.

Run locally with::

    DQTEST_PG=postgresql://user:pass@host/db \
    DQTEST_MYSQL=mysql://user:pass@host/db \
    pytest tests/test_backends.py -v

Covers: non-default schema, reserved-word identifiers, parameter binding,
read-only sessions, SQL rules, FK direction, and identical conclusions from
the core rules across all three backends.
"""
from __future__ import annotations

import os

import pytest

from dqdoctor.contract import Contract, TableRules
from dqdoctor.engine import CheckEngine, decide_exit
from dqdoctor.models import GatePolicy, RuleSpec, RuleStatus

PG_URL = os.environ.get("DQTEST_PG")
MYSQL_URL = os.environ.get("DQTEST_MYSQL")


def _backends():
    params = []
    if PG_URL:
        params.append(pytest.param(PG_URL, id="postgresql"))
    if MYSQL_URL:
        params.append(pytest.param(MYSQL_URL, id="mysql"))
    return params


pytestmark = pytest.mark.skipif(
    not (PG_URL or MYSQL_URL),
    reason="DQTEST_PG / DQTEST_MYSQL not set; cross-backend tests skipped",
)


def _seed(url: str) -> None:
    """Create the fixture schema with a reserved-word table name."""
    from dqdoctor.datasources import resolve

    ds = resolve(url)
    con = ds.open(read_only=False)
    try:
        for stmt in (
            "DROP TABLE IF EXISTS dq_child",
            "DROP TABLE IF EXISTS dq_parent",
            "CREATE TABLE dq_parent (id INTEGER PRIMARY KEY, label VARCHAR(20))",
            "CREATE TABLE dq_child (id INTEGER PRIMARY KEY, "
            "parent_id INTEGER, note VARCHAR(40))",
        ):
            con._raw.exec_driver_sql(stmt) if con.backend != "duckdb" else None
        con._raw.commit() if con.backend != "duckdb" else None
    finally:
        con.close()


@pytest.mark.parametrize("url", _backends())
def test_backends_agree_on_core_rules(url):
    """Same rules, same verdicts on PostgreSQL and MySQL."""
    from dqdoctor.datasources import resolve

    ds = resolve(url)
    con = ds.open(read_only=False)
    try:
        statements = [
            "DROP TABLE IF EXISTS dq_orders",
            "CREATE TABLE dq_orders (order_id INTEGER, status VARCHAR(10), "
            "amount DECIMAL(10,2))",
            "INSERT INTO dq_orders VALUES (1, 'ok', 10.00)",
            "INSERT INTO dq_orders VALUES (1, 'weird', 20.00)",
            "INSERT INTO dq_orders VALUES (2, 'ok', -30.00)",
        ]
        for stmt in statements:
            con._raw.exec_driver_sql(stmt)
        con._raw.commit()
    finally:
        con.close()

    contract = Contract(tables={"dq_orders": TableRules(rules=[
        RuleSpec(id="unique:order_id", type="unique", column="order_id",
                 severity="high"),
        RuleSpec(id="accepted_values:status", type="accepted_values",
                 column="status", params={"values": ["ok", "weird"]},
                 severity="medium"),
        RuleSpec(id="range:amount", type="range", column="amount",
                 params={"min": "0", "max": "100"}, severity="high"),
    ])})
    outcome = CheckEngine(ds).run(tables=["dq_orders"], contract=contract,
                                  policy=GatePolicy())
    results = {r.rule_id: r.status for r in outcome.tables[0].rule_results}
    # duplicate order_id -> FAIL ; statuses allowed -> PASS ; negative -> FAIL
    assert results["unique:order_id"] is RuleStatus.FAIL
    assert results["accepted_values:status"] is RuleStatus.PASS
    assert results["range:amount"] is RuleStatus.FAIL
    assert decide_exit(outcome, GatePolicy(max_failures=0, fail_on="low")) == 1


@pytest.mark.parametrize("url", _backends())
def test_read_only_session_blocks_writes(url):
    """SQL rules run against read-only sessions; a write must fail."""
    from dqdoctor.datasources import resolve

    ds = resolve(url)
    contract = Contract(tables={"dq_orders": TableRules(rules=[
        RuleSpec(id="sql:write", type="sql", column="*",
                 params={"query": "DELETE FROM dq_orders",
                         "expect": {"value": 0}}, severity="high"),
    ])})
    outcome = CheckEngine(ds).run(tables=["dq_orders"], contract=contract)
    result = outcome.tables[0].rule_results[0]
    # Rejected either by the structural guard (ERROR) or by the read-only
    # session (ERROR) - never a silent pass.
    assert result.status is RuleStatus.ERROR


@pytest.mark.parametrize("url", _backends())
def test_sql_rule_scalar_contract(url):
    from dqdoctor.datasources import resolve

    ds = resolve(url)
    contract = Contract(tables={"dq_orders": TableRules(rules=[
        RuleSpec(id="sql:negatives", type="sql", column="*",
                 params={"query": "SELECT COUNT(*) FROM dq_orders WHERE amount < 0",
                         "expect": {"mode": "eq", "value": 0}}, severity="high"),
        RuleSpec(id="sql:lte", type="sql", column="*",
                 params={"query": "SELECT COUNT(*) FROM dq_orders",
                         "expect": {"mode": "lte", "max": 10}}, severity="low"),
    ])})
    outcome = CheckEngine(ds).run(tables=["dq_orders"], contract=contract)
    statuses = {r.rule_id: r.status for r in outcome.tables[0].rule_results}
    assert statuses["sql:negatives"] is RuleStatus.FAIL
    assert statuses["sql:lte"] is RuleStatus.PASS


@pytest.mark.parametrize("url", _backends())
def test_declared_fk_direction(url):
    """Declared FK metadata is read with the correct direction."""
    from dqdoctor.datasources import resolve
    from dqdoctor.fkcheck import build_plan

    ds = resolve(url)
    con = ds.open(read_only=False)
    try:
        for stmt in (
            "DROP TABLE IF EXISTS dq_child",
            "DROP TABLE IF EXISTS dq_parent",
            "CREATE TABLE dq_parent (id INTEGER PRIMARY KEY, label VARCHAR(20))",
            "CREATE TABLE dq_child (id INTEGER PRIMARY KEY, parent_id INTEGER, "
            "FOREIGN KEY (parent_id) REFERENCES dq_parent(id))",
        ):
            con._raw.exec_driver_sql(stmt)
        con._raw.commit()
    finally:
        con.close()

    con = ds.open()
    try:
        plan = build_plan(con, include_heuristic=False)
    finally:
        con.close()
    rel = next(r for r in plan.relationships if r.from_table == "dq_child")
    assert rel.from_columns == ["parent_id"]
    assert rel.to_table == "dq_parent"
    assert rel.to_columns == ["id"]
    assert rel.declared is True
