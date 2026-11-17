"""SQL rule guardrails and new rule types (DuckDB path)."""
from __future__ import annotations

import duckdb
import pytest

from dqdoctor.contract import Contract, TableRules
from dqdoctor.datasources import DataSource, parse_spec
from dqdoctor.engine import CheckEngine
from dqdoctor.models import RuleSpec, RuleStatus


@pytest.fixture()
def sales_db(tmp_root):
    path = tmp_root / "sales.duckdb"
    con = duckdb.connect(str(path))
    con.execute(
        "CREATE TABLE sales (id INTEGER, qty INTEGER, price DECIMAL(10,2),"
        " status VARCHAR, ordered_at TIMESTAMP)"
    )
    con.execute(
        "INSERT INTO sales VALUES"
        " (1, 5, 10.00, 'paid', TIMESTAMP '2026-11-17 10:00:00'),"
        " (2, 3, 20.00, 'paid', TIMESTAMP '2026-11-17 09:00:00'),"
        " (3, 0, 30.00, 'refunded', TIMESTAMP '2026-11-17 08:00:00')"
    )
    con.close()
    return path


def _run(path, rules):
    contract = Contract(tables={"sales": TableRules(rules=rules)})
    ds = DataSource(parse_spec(str(path)))
    return CheckEngine(ds).run(tables=["sales"], contract=contract)


def test_sql_eq_lte_gte_between(sales_db):
    outcome = _run(sales_db, [
        RuleSpec(id="sql:eq", type="sql", column="*",
                 params={"query": "SELECT COUNT(*) FROM sales WHERE qty < 0",
                         "expect": {"mode": "eq", "value": 0}}, severity="high"),
        RuleSpec(id="sql:lte", type="sql", column="*",
                 params={"query": "SELECT COUNT(*) FROM sales",
                         "expect": {"mode": "lte", "max": 10}}, severity="low"),
        RuleSpec(id="sql:gte", type="sql", column="*",
                 params={"query": "SELECT COUNT(*) FROM sales",
                         "expect": {"mode": "gte", "min": 10}}, severity="low"),
        RuleSpec(id="sql:between", type="sql", column="*",
                 params={"query": "SELECT SUM(qty) FROM sales",
                         "expect": {"mode": "between", "min": 1, "max": 100}},
                 severity="medium"),
    ])
    statuses = {r.rule_id: r.status for r in outcome.tables[0].rule_results}
    assert statuses["sql:eq"] is RuleStatus.PASS
    assert statuses["sql:lte"] is RuleStatus.PASS
    assert statuses["sql:gte"] is RuleStatus.FAIL
    assert statuses["sql:between"] is RuleStatus.PASS


def test_sql_rule_non_scalar_is_error(sales_db):
    outcome = _run(sales_db, [
        RuleSpec(id="sql:many", type="sql", column="*",
                 params={"query": "SELECT id, qty FROM sales",
                         "expect": {"value": 0}}, severity="high"),
    ])
    result = outcome.tables[0].rule_results[0]
    assert result.status is RuleStatus.ERROR
    assert "scalar" in result.message.lower()


def test_sql_rule_missing_expect_is_skip(sales_db):
    outcome = _run(sales_db, [
        RuleSpec(id="sql:noexpect", type="sql", column="*",
                 params={"query": "SELECT COUNT(*) FROM sales"},
                 severity="high"),
    ])
    assert outcome.tables[0].rule_results[0].status is RuleStatus.SKIP


def test_regex_rule(sales_db):
    outcome = _run(sales_db, [
        RuleSpec(id="regex:status", type="regex", column="status",
                 params={"pattern": "^(paid|refunded)$"}, severity="medium"),
        RuleSpec(id="regex:bad", type="regex", column="status",
                 params={"pattern": "^paid$"}, severity="high"),
    ])
    statuses = {r.rule_id: r.status for r in outcome.tables[0].rule_results}
    assert statuses["regex:status"] is RuleStatus.PASS
    assert statuses["regex:bad"] is RuleStatus.FAIL


def test_row_count_rule(sales_db):
    outcome = _run(sales_db, [
        RuleSpec(id="rc:min", type="row_count", column="*",
                 params={"min": 10}, severity="high"),
        RuleSpec(id="rc:ok", type="row_count", column="*",
                 params={"min": 1, "max": 100}, severity="medium"),
        RuleSpec(id="rc:exact", type="row_count", column="*",
                 params={"exact": 3}, severity="low"),
    ])
    statuses = {r.rule_id: r.status for r in outcome.tables[0].rule_results}
    assert statuses["rc:min"] is RuleStatus.FAIL
    assert statuses["rc:ok"] is RuleStatus.PASS
    assert statuses["rc:exact"] is RuleStatus.PASS


def test_cross_field_rule(sales_db):
    outcome = _run(sales_db, [
        # a refund must not carry positive qty
        RuleSpec(id="cross:refund", type="cross_field", column="*",
                 params={"left": "qty", "right": "id", "op": ">="},
                 severity="medium"),
    ])
    result = outcome.tables[0].rule_results[0]
    assert result.status is RuleStatus.FAIL
    assert "violated on 1/3" in result.message


def test_cross_field_unknown_column_is_error(sales_db):
    outcome = _run(sales_db, [
        RuleSpec(id="cross:bad", type="cross_field", column="*",
                 params={"left": "nope", "right": "id", "op": ">="},
                 severity="medium"),
    ])
    assert outcome.tables[0].rule_results[0].status is RuleStatus.ERROR


def test_cross_field_rejects_bad_operator(sales_db):
    outcome = _run(sales_db, [
        RuleSpec(id="cross:op", type="cross_field", column="*",
                 params={"left": "qty", "right": "id", "op": "DROP"},
                 severity="medium"),
    ])
    assert outcome.tables[0].rule_results[0].status is RuleStatus.SKIP


def test_decimal_precision_survives_generation_and_load(tmp_root):
    """Decimal boundaries keep exact values through save/load/execute."""
    from dqdoctor.contract import load_contract, save_contract

    path = tmp_root / "p.duckdb"
    con = duckdb.connect(str(path))
    con.execute("CREATE TABLE t (v DECIMAL(20,10))")
    con.execute("INSERT INTO t VALUES (0.1234567891), (0.9999999999)")
    con.close()
    contract = Contract(tables={"t": TableRules(rules=[
        RuleSpec(id="range:v", type="range", column="v",
                 params={"min": "0.1234567890", "max": "1.0000000000"},
                 severity="high"),
    ])})
    saved = save_contract(contract, tmp_root / "c.yml")
    loaded = load_contract(saved)
    ds = DataSource(parse_spec(str(path)))
    outcome = CheckEngine(ds).run(tables=["t"], contract=loaded)
    assert outcome.tables[0].rule_results[0].status is RuleStatus.PASS
