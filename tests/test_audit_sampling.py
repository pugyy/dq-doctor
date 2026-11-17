"""Audit P0-1: sampling must never influence a rule verdict."""
from __future__ import annotations

from datetime import UTC, datetime

import duckdb
import pytest

from dqdoctor.contract import Contract, TableRules
from dqdoctor.datasources import DataSource, parse_spec
from dqdoctor.engine import CheckEngine
from dqdoctor.models import RuleSpec, RuleStatus


def _clock():
    return datetime(2026, 11, 17, 12, tzinfo=UTC)


@pytest.fixture()
def sampled_db(tmp_root):
    path = tmp_root / "samp.duckdb"
    con = duckdb.connect(str(path))
    con.execute("CREATE TABLE t (id INTEGER, amount DECIMAL(10,2))")
    con.execute("INSERT INTO t SELECT range, range * 1.5 FROM range(1000)")
    con.execute("UPDATE t SET id = NULL WHERE id < 100")
    con.close()
    return path


def test_contract_mode_ignores_sample_rows(sampled_db):
    contract = Contract(tables={"t": TableRules(rules=[
        RuleSpec(id="u:id", type="unique", column="id", severity="high"),
        RuleSpec(id="nn:id", type="not_null", column="id", severity="high"),
        RuleSpec(id="r:amount", type="range", column="amount",
                 params={"min": 0, "max": 5000}, severity="low"),
    ])})
    engine = CheckEngine(DataSource(parse_spec(str(sampled_db))), clock=_clock)
    table = engine.run(tables=["t"], contract=contract, sample_rows=50).tables[0]

    assert table.profile.sampling.method == "full", (
        "contract mode must profile the full table, not the sample"
    )
    results = {r.rule_id: r for r in table.rule_results}
    # 900 non-null distinct values: a sampled profile would report 850
    # "duplicates" and fail this rule.
    assert results["u:id"].status is RuleStatus.PASS, results["u:id"].message
    assert results["nn:id"].failed_count == 100, results["nn:id"].message
    assert results["r:amount"].status is RuleStatus.PASS


def test_explore_mode_marks_sampled_profile(sampled_db):
    engine = CheckEngine(DataSource(parse_spec(str(sampled_db))), clock=_clock)
    table = engine.run(tables=["t"], explore=True, sample_rows=50).tables[0]
    assert table.profile.sampling.method == "sample"
    assert table.profile.sampling.random is False
    assert table.profile.row_count == 1000


def test_column_counters_record_their_own_row_count(sampled_db):
    """A column counter can never be compared against the table row count."""
    engine = CheckEngine(DataSource(parse_spec(str(sampled_db))), clock=_clock)
    table = engine.run(tables=["t"], explore=True, sample_rows=50).tables[0]
    col = table.profile.column("id")
    assert col is not None
    assert col.stats_row_count == 50
    assert table.profile.row_count == 1000
