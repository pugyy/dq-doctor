"""Coverage for gate, drift and demo modules (audit follow-up)."""
from __future__ import annotations

from datetime import UTC, datetime

import duckdb
import pytest


def _clock():
    return datetime(2026, 11, 17, 12, tzinfo=UTC)


# --- gate.run_gate --------------------------------------------------------


@pytest.fixture()
def gate_db(tmp_root):
    path = tmp_root / "g.duckdb"
    con = duckdb.connect(str(path))
    con.execute("CREATE TABLE t (id INTEGER)")
    con.execute("INSERT INTO t VALUES (1), (2)")
    con.close()
    return path


def test_run_gate_passes_and_writes_report(gate_db, tmp_root):
    from dqdoctor.gate import run_gate

    out = tmp_root / "summary.json"
    summary = run_gate(source=str(gate_db), table_name="t", out_path=str(out))
    # No contract -> explore mode: nothing executed, so no score (correct).
    assert summary["t"]["score"] is None
    assert summary["t"]["failed"] == 0
    assert out.exists()


def test_run_gate_with_contract_reports_a_score(gate_db, tmp_root):
    from dqdoctor.contract import Contract, TableRules, save_contract
    from dqdoctor.gate import run_gate
    from dqdoctor.models import RuleSpec

    contract = Contract(tables={"t": TableRules(rules=[
        RuleSpec(id="nn:id", type="not_null", column="id", severity="high"),
    ])})
    cfg = save_contract(contract, tmp_root / "ok.yml")
    summary = run_gate(source=str(gate_db), table_name="t", rules_path=str(cfg),
                       out_path=str(tmp_root / "s.json"))
    assert summary["t"]["score"] == 100
    assert summary["t"]["passed"] == 1


def test_run_gate_trips_on_failure(gate_db, tmp_root):
    from dqdoctor.contract import Contract, TableRules, save_contract
    from dqdoctor.gate import QualityGateError, run_gate
    from dqdoctor.models import RuleSpec

    contract = Contract(tables={"t": TableRules(rules=[
        RuleSpec(id="r:id", type="range", column="id",
                 params={"min": 100, "max": 200}, severity="high"),
    ])})
    cfg = save_contract(contract, tmp_root / "c.yml")
    with pytest.raises(QualityGateError):
        run_gate(source=str(gate_db), table_name="t", rules_path=str(cfg),
                 out_path=str(tmp_root / "s.json"))


def test_run_gate_raises_runner_error_for_bad_source(tmp_root):
    from dqdoctor.gate import RunnerError, run_gate

    with pytest.raises(RunnerError):
        run_gate(source=str(tmp_root / "missing.duckdb"), table_name="t",
                 out_path=str(tmp_root / "s.json"))


def test_run_gate_requires_a_table(gate_db, tmp_root):
    from dqdoctor.gate import RunnerError, run_gate

    with pytest.raises(RunnerError):
        run_gate(source=str(gate_db), out_path=str(tmp_root / "s.json"))


def test_summarize_counts_statuses(gate_db):
    from dqdoctor.datasources import DataSource, parse_spec
    from dqdoctor.engine import CheckEngine
    from dqdoctor.gate import summarize

    outcome = CheckEngine(DataSource(parse_spec(str(gate_db))), clock=_clock).run(
        tables=["t"], explore=True
    )
    summary = summarize(outcome)
    assert summary["t"]["passed"] == 0
    assert "score" in summary["t"]


# --- drift ----------------------------------------------------------------


def test_drift_detects_column_and_row_changes(tmp_root):
    from dqdoctor.datasources import DataSource, parse_spec
    from dqdoctor.drift import compare_profiles, load_profile, save_profile
    from dqdoctor.profiling import profile_table

    def build(name, values):
        path = tmp_root / name
        con = duckdb.connect(str(path))
        con.execute("CREATE TABLE d (id INTEGER, label VARCHAR)")
        con.executemany("INSERT INTO d VALUES (?, ?)", values)
        con.close()
        ds = DataSource(parse_spec(str(path)))
        con = ds.open()
        try:
            return profile_table(con, ds.describe(), "d")
        finally:
            con.close()

    old = build("old.duckdb", [(1, "a"), (2, "b")])
    new = build("new.duckdb", [(1, "a"), (2, None), (3, "c"), (4, "d")])

    old_path = save_profile(old, tmp_root / "old.json")
    new_path = save_profile(new, tmp_root / "new.json")
    result = compare_profiles(load_profile(old_path), load_profile(new_path))

    assert result.table_name == "d"
    metrics = {d.metric for d in result.drifts}
    assert "row_count" in metrics
    assert "null_rate" in metrics
    assert "high" in result.summary or "medium" in result.summary


def test_drift_refuses_different_tables(tmp_root):
    from dqdoctor.drift import compare_profiles
    from dqdoctor.models import TableProfile

    a = TableProfile(datasource="x", table_name="a", row_count=1, columns=[])
    b = TableProfile(datasource="y", table_name="b", row_count=1, columns=[])
    result = compare_profiles(a, b)
    assert "cannot compare" in result.summary.lower()


# --- demo -----------------------------------------------------------------


def test_demo_and_dirty_demo_are_queryable(tmp_root):
    from dqdoctor import demo

    clean = demo.create_demo_db(str(tmp_root / "demo.duckdb"))
    dirty = demo.create_dirty_db(str(tmp_root / "dirty.duckdb"))
    assert clean.exists() and dirty.exists()
    assert demo.list_tables(clean)
    assert demo.list_tables(dirty)


def test_demo_missing_database_raises(tmp_root):
    from dqdoctor import demo

    with pytest.raises(FileNotFoundError):
        demo.list_tables(tmp_root / "nope.duckdb")


# --- dashboard ------------------------------------------------------------


def test_dashboard_requires_flask_or_serves(tmp_root):
    from dqdoctor.datasources import DataSource, parse_spec
    from dqdoctor.engine import CheckEngine
    from dqdoctor.outputs import write_json

    db = tmp_root / "d.duckdb"
    con = duckdb.connect(str(db))
    con.execute("CREATE TABLE t (id INTEGER)")
    con.execute("INSERT INTO t VALUES (1)")
    con.close()
    outcome = CheckEngine(DataSource(parse_spec(str(db))), clock=_clock).run(
        tables=["t"], explore=True
    )
    report = write_json(outcome, tmp_root / "r.json")

    from dqdoctor.dashboard import run_dashboard

    try:
        import flask  # noqa: F401
    except ImportError:
        with pytest.raises(ImportError):
            run_dashboard(report)
        return
    # Flask installed: only verify the file is accepted, do not bind a port.
    assert report.exists()


def test_dashboard_missing_report_raises(tmp_root):
    from dqdoctor.dashboard import run_dashboard

    try:
        import flask  # noqa: F401
    except ImportError:
        pytest.skip("flask not installed")
    with pytest.raises(FileNotFoundError):
        run_dashboard(tmp_root / "nope.json")


# --- mcp ------------------------------------------------------------------


def test_mcp_server_requires_sdk(tmp_root):
    from dqdoctor import mcp_server

    try:
        import mcp  # noqa: F401
    except ImportError:
        with pytest.raises(ImportError, match="MCP SDK"):
            mcp_server.serve(tmp_root / ".dqdoctor.yml")
        return
    assert hasattr(mcp_server, "serve")


def test_mcp_resolve_uses_registry(tmp_root, monkeypatch):
    from dqdoctor import mcp_server

    monkeypatch.chdir(tmp_root)
    (tmp_root / ".dqdoctor.yml").write_text(
        "datasources:\n  local: demo.duckdb\ndefault: local\n", encoding="utf-8"
    )
    ds = mcp_server._resolve("local", tmp_root / ".dqdoctor.yml")
    assert ds.spec.path is not None
    assert ds.spec.path.name == "demo.duckdb"
