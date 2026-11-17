"""Audit P0-5/6/7: FK gating and exit-code contract."""
from __future__ import annotations

from datetime import UTC, datetime

import duckdb
import pytest
from typer.testing import CliRunner

from dqdoctor import baseline as baseline_mod
from dqdoctor.cli import app
from dqdoctor.contract import Contract, TableRules, save_contract
from dqdoctor.datasources import DataSource, parse_spec
from dqdoctor.engine import CheckEngine, decide_exit
from dqdoctor.models import GatePolicy, RuleSpec


def _clock():
    return datetime(2026, 11, 17, 12, tzinfo=UTC)


@pytest.fixture()
def orphan_db(tmp_root):
    path = tmp_root / "fk.duckdb"
    con = duckdb.connect(str(path))
    con.execute("CREATE TABLE parents (id INTEGER)")
    con.execute("CREATE TABLE children (parent_id INTEGER)")
    con.execute("INSERT INTO parents VALUES (1)")
    con.execute("INSERT INTO children VALUES (1), (2)")
    con.close()
    return path


def test_fk_orphans_gate_without_baseline(orphan_db):
    engine = CheckEngine(
        DataSource(parse_spec(str(orphan_db))), clock=_clock, include_heuristic_fk=True
    )
    outcome = engine.run(tables=["children"], explore=True)
    assert [fk for fk in outcome.fk_issues if fk.orphan_rows > 0]
    policy = GatePolicy(max_failures=0, fail_on="low")
    assert decide_exit(outcome, policy) == 1, "orphans must gate with no baseline"
    assert decide_exit(outcome, policy, None) == 1


def test_fk_baseline_exempts_only_known_pairs(orphan_db):
    engine = CheckEngine(
        DataSource(parse_spec(str(orphan_db))), clock=_clock, include_heuristic_fk=True
    )
    outcome = engine.run(tables=["children"], explore=True)
    base = baseline_mod.capture(outcome, "now")
    assert base.fk_entries, "the orphan pair should be captured"

    policy = GatePolicy(max_failures=0, fail_on="low")
    tolerated = engine.run(tables=["children"], explore=True, baseline=base,
                           policy=policy)
    assert decide_exit(tolerated, policy, base) == 0

    with duckdb.connect(str(orphan_db)) as con:
        con.execute("INSERT INTO children VALUES (3)")
    deteriorated = engine.run(tables=["children"], explore=True, baseline=base, policy=policy)
    assert decide_exit(deteriorated, policy, base) == 1


@pytest.fixture()
def failing_sql_contract(tmp_root):
    db = tmp_root / "e.duckdb"
    con = duckdb.connect(str(db))
    con.execute("CREATE TABLE e (v INTEGER)")
    con.execute("INSERT INTO e VALUES (1)")
    con.close()
    contract = Contract(tables={"e": TableRules(rules=[
        RuleSpec(id="sql:boom", type="sql", column="*",
                 params={"query": "SELECT nope FROM e",
                         "expect": {"mode": "eq", "value": 0}},
                 severity="high"),
    ])})
    return db, save_contract(contract, tmp_root / "c.yml")


def test_rule_error_exits_two_without_ci(failing_sql_contract, tmp_root):
    db, cfg = failing_sql_contract
    result = CliRunner().invoke(app, [
        "check", "--db", str(db), "--table", "e", "--rules", str(cfg),
        "--out", str(tmp_root / "r.html"),
    ])
    assert result.exit_code == 2, result.output


def test_rule_error_exits_two_with_ci(failing_sql_contract, tmp_root):
    db, cfg = failing_sql_contract
    result = CliRunner().invoke(app, [
        "check", "--db", str(db), "--table", "e", "--rules", str(cfg),
        "--out", str(tmp_root / "r.html"), "--ci",
    ])
    assert result.exit_code == 2, result.output


def test_low_failure_does_not_gate_fail_on_high(tmp_root):
    db = tmp_root / "f.duckdb"
    con = duckdb.connect(str(db))
    con.execute("CREATE TABLE f (v INTEGER)")
    con.execute("INSERT INTO f VALUES (1), (2)")
    con.close()
    contract = Contract(tables={"f": TableRules(rules=[
        RuleSpec(id="r:v", type="range", column="v",
                 params={"min": 100, "max": 200}, severity="low"),
    ])})
    cfg = save_contract(contract, tmp_root / "f.yml")
    result = CliRunner().invoke(app, [
        "check", "--db", str(db), "--table", "f", "--rules", str(cfg),
        "--out", str(tmp_root / "f.html"), "--ci", "--fail-on", "high",
    ])
    assert result.exit_code == 0, result.output
    assert "gate tripped" not in result.output


def test_high_failure_gates_fail_on_high(tmp_root):
    db = tmp_root / "g.duckdb"
    con = duckdb.connect(str(db))
    con.execute("CREATE TABLE g (v INTEGER)")
    con.execute("INSERT INTO g VALUES (1), (2)")
    con.close()
    contract = Contract(tables={"g": TableRules(rules=[
        RuleSpec(id="r:v", type="range", column="v",
                 params={"min": 100, "max": 200}, severity="high"),
    ])})
    cfg = save_contract(contract, tmp_root / "g.yml")
    result = CliRunner().invoke(app, [
        "check", "--db", str(db), "--table", "g", "--rules", str(cfg),
        "--out", str(tmp_root / "g.html"), "--ci", "--fail-on", "high",
    ])
    assert result.exit_code == 1, result.output
