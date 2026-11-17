"""Regressions for the specific 0.7 bugs reproduced before the rewrite."""
from __future__ import annotations

from datetime import UTC, datetime

import duckdb
import pytest

from dqdoctor.datasources import DataSource, parse_spec
from dqdoctor.engine import CheckEngine
from dqdoctor.models import RuleSpec, RuleStatus
from dqdoctor.pii import detect_pii
from dqdoctor.profiling import infer_semantic_type


def _clock():
    return datetime(2026, 11, 17, 12, 0, 0, tzinfo=UTC)


def _engine(path):
    return CheckEngine(DataSource(parse_spec(str(path))), clock=_clock)


@pytest.fixture()
def bug_db(tmp_root):
    """The exact 0.7 trap columns: nullable unique, TIME, version, int time."""
    path = tmp_root / "bugs.duckdb"
    con = duckdb.connect(str(path))
    con.execute(
        """
        CREATE TABLE t1 (
            id INTEGER,
            email VARCHAR,
            call_time TIME,
            agent_version VARCHAR,
            estimated_time_minutes INTEGER,
            birth_date DATE,
            status VARCHAR
        );
        INSERT INTO t1 VALUES
            (1, 'a@x.com', TIME '12:34:56', '1.2.3.4', 30, DATE '1990-05-01', 'ok'),
            (2, 'b@x.com', TIME '01:02:03', '2.0.1',   45, DATE '1985-12-30', 'ok'),
            (3, NULL,      TIME '23:59:59', '10.0.0.1', 60, DATE '2000-01-01', 'bad');
        """
    )
    con.close()
    return path


def test_unique_ignores_nulls(bug_db):
    """0.7 counted NULLs as duplicates: a nullable unique column failed."""
    result = _engine(bug_db).run(
        tables=["t1"],
        contract=None,
        explore=False,
    )
    # build an explicit contract with a nullable unique column
    from dqdoctor.contract import Contract, TableRules

    contract = Contract(
        tables={"t1": TableRules(rules=[
            RuleSpec(id="u:email", type="unique", column="email", severity="high"),
        ])}
    )
    outcome = _engine(bug_db).run(tables=["t1"], contract=contract)
    res = outcome.tables[0].rule_results[0]
    assert res.status is RuleStatus.PASS, res.message
    assert "non-null" in res.message
    assert result is not None


def test_freshness_on_integer_column_does_not_crash(bug_db):
    """0.7 raised TypeError on `datetime - int` and killed the whole check."""
    from dqdoctor.contract import Contract, TableRules

    contract = Contract(
        tables={"t1": TableRules(rules=[
            RuleSpec(id="f:int", type="freshness", column="estimated_time_minutes",
                     params={"max_age_hours": 24}, severity="high"),
        ])}
    )
    outcome = _engine(bug_db).run(tables=["t1"], contract=contract)
    res = outcome.tables[0].rule_results[0]
    assert res.status is RuleStatus.SKIP
    assert "TIMESTAMP/DATE" in res.message


def test_freshness_on_time_column_skipped(bug_db):
    from dqdoctor.contract import Contract, TableRules

    contract = Contract(
        tables={"t1": TableRules(rules=[
            RuleSpec(id="f:time", type="freshness", column="call_time",
                     params={"max_age_hours": 24}, severity="high"),
        ])}
    )
    outcome = _engine(bug_db).run(tables=["t1"], contract=contract)
    assert outcome.tables[0].rule_results[0].status is RuleStatus.SKIP


def test_semantics_do_not_learn_freshness_from_names_alone():
    """Only real temporal dtypes become event_time."""
    assert infer_semantic_type("estimated_time_minutes", "INTEGER") == "unknown"
    assert infer_semantic_type("call_time", "TIME") == "unknown"
    assert infer_semantic_type("birth_date", "DATE") == "birthdate"
    assert infer_semantic_type("created_at", "TIMESTAMP") == "event_time"


def test_pii_time_values_are_not_ipv6():
    assert detect_pii("call_time", ["12:34:56", "01:02:03"]) is None


def test_pii_version_strings_are_not_ip():
    assert detect_pii("agent_version", ["1.2.3.4", "2.0.1"]) is None


def test_pii_invalid_ipv4_rejected():
    assert detect_pii("ip_addr", ["999.999.999.999"]) is None
    assert detect_pii("ip_addr", ["10.0.0.1", "192.168.1.1"]) is not None


def test_pii_hint_falls_through_to_patterns():
    """0.7's 'tel' hint hijacked hotel_id and aborted detection."""
    assert detect_pii("hotel_id", ["H100", "H200"]) is None
    # a genuine phone column still detects
    evidence = detect_pii("contact_tel", ["13800138000", "13900139000"])
    assert evidence is not None and evidence.pii_type == "phone_cn"


def test_empty_table_pass_not_suggestion():
    """0.7 reported executed-on-empty rules as SUGGEST (total_count == 0)."""
    import tempfile
    from pathlib import Path

    path = Path(tempfile.mkdtemp()) / "empty.duckdb"
    con = duckdb.connect(str(path))
    con.execute("CREATE TABLE e (id INTEGER NOT NULL)")
    con.close()
    from dqdoctor.contract import Contract, TableRules

    contract = Contract(
        tables={"e": TableRules(rules=[
            RuleSpec(id="nn:id", type="not_null", column="id", severity="high"),
        ])}
    )
    outcome = _engine(path).run(tables=["e"], contract=contract)
    table = outcome.tables[0]
    assert table.rule_results[0].status is RuleStatus.PASS
    assert table.score == 100


def test_sql_rule_returning_zero_is_a_real_pass(bug_db):
    from dqdoctor.contract import Contract, TableRules

    contract = Contract(
        tables={"t1": TableRules(rules=[
            RuleSpec(id="sql:zero", type="sql", column="*",
                     params={"query": "SELECT COUNT(*) FROM t1 WHERE id < 0",
                             "expect": {"mode": "eq", "value": 0}},
                     severity="high"),
        ])}
    )
    outcome = _engine(bug_db).run(tables=["t1"], contract=contract)
    res = outcome.tables[0].rule_results[0]
    assert res.status is RuleStatus.PASS
    assert "got 0" in res.message


def test_sql_rule_write_rejected(bug_db):
    from dqdoctor.contract import Contract, TableRules

    contract = Contract(
        tables={"t1": TableRules(rules=[
            RuleSpec(id="sql:del", type="sql", column="*",
                     params={"query": "DELETE FROM t1", "expect": {"value": 0}},
                     severity="high"),
        ])}
    )
    outcome = _engine(bug_db).run(tables=["t1"], contract=contract)
    res = outcome.tables[0].rule_results[0]
    assert res.status is RuleStatus.ERROR
    assert "SELECT/WITH" in res.message


def test_sql_rule_multi_statement_rejected(bug_db):
    from dqdoctor.contract import Contract, TableRules

    contract = Contract(
        tables={"t1": TableRules(rules=[
            RuleSpec(id="sql:multi", type="sql", column="*",
                     params={"query": "SELECT 1; DROP TABLE t1",
                             "expect": {"value": 0}},
                     severity="high"),
        ])}
    )
    outcome = _engine(bug_db).run(tables=["t1"], contract=contract)
    assert outcome.tables[0].rule_results[0].status is RuleStatus.ERROR


def test_multiple_rules_same_column_kept(tmp_root):
    """0.7 deduped (type, column) and silently dropped one of two rules."""
    from dqdoctor.contract import Contract, TableRules

    path = tmp_root / "m.duckdb"
    con = duckdb.connect(str(path))
    con.execute("CREATE TABLE m (v INTEGER); INSERT INTO m VALUES (1),(2),(3);")
    con.close()
    contract = Contract(
        tables={"m": TableRules(rules=[
            RuleSpec(id="range:low", type="range", column="v",
                     params={"min": 0, "max": 10}, severity="medium"),
            RuleSpec(id="range:high", type="range", column="v",
                     params={"min": 100, "max": 200}, severity="high"),
        ])}
    )
    outcome = _engine(path).run(tables=["m"], contract=contract)
    results = outcome.tables[0].rule_results
    assert len(results) == 2
    assert {r.rule_id for r in results} == {"range:low", "range:high"}
    assert results[0].status is RuleStatus.PASS
    assert results[1].status is RuleStatus.FAIL


def test_demo_refuses_overwrite(tmp_root, monkeypatch):
    """0.7 unlinked any existing file passed via --output."""
    from typer.testing import CliRunner

    from dqdoctor.cli import app

    target = tmp_root / "victim.duckdb"
    target.write_bytes(b"precious")
    runner = CliRunner()
    result = runner.invoke(app, ["demo", "--output", str(target)])
    assert result.exit_code == 2
    assert target.read_bytes() == b"precious"


def test_demo_force_overwrites(tmp_root):
    from typer.testing import CliRunner

    from dqdoctor.cli import app

    target = tmp_root / "ok.duckdb"
    target.write_bytes(b"old")
    result = CliRunner().invoke(app, ["demo", "--output", str(target), "--force"])
    assert result.exit_code == 0
    assert target.stat().st_size > 100
