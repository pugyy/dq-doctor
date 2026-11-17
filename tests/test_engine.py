"""Engine, contract, scoring, baseline and exit-code tests."""
from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from dqdoctor import baseline as baseline_mod
from dqdoctor.contract import Contract, TableRules, load_contract, save_contract
from dqdoctor.datasources import DataSource, parse_spec
from dqdoctor.engine import CheckEngine, decide_exit
from dqdoctor.models import GatePolicy, RuleSpec, RuleStatus
from dqdoctor.scoring import score_table


def _engine(path, clock=None):
    from tests.conftest import fixed_clock

    return CheckEngine(DataSource(parse_spec(str(path))), clock=clock or fixed_clock)


def _contract(table, rules):
    return Contract(tables={table: TableRules(rules=rules)})


# --- explore vs contract ---------------------------------------------------


def test_explore_mode_marks_everything_as_suggestion(clean_db):
    outcome = _engine(clean_db).run(tables=["orders"], explore=True)
    table = outcome.tables[0]
    assert table.rule_results, "expected suggestions"
    assert all(r.status is RuleStatus.SUGGESTION for r in table.rule_results)
    assert table.score is None, "nothing executed -> no score"


def test_contract_mode_learns_nothing_from_batch(clean_db):
    contract = _contract("orders", [
        RuleSpec(id="range:total_amount", type="range", column="total_amount",
                 params={"min": "0.00", "max": "25.00"}, severity="high"),
    ])
    outcome = _engine(clean_db).run(tables=["orders"], contract=contract)
    res = outcome.tables[0].rule_results[0]
    # 30.00 exists in this batch: the pinned max must trip despite profiling
    assert res.status is RuleStatus.FAIL
    assert "30" in res.message or "outside" in res.message


# --- scoring ---------------------------------------------------------------


def test_score_none_without_executed_rules(clean_db):
    outcome = _engine(clean_db).run(tables=["orders"], explore=True)
    assert outcome.tables[0].score is None


def test_score_is_severity_weighted(clean_db):
    contract = _contract("orders", [
        RuleSpec(id="nn:a", type="not_null", column="order_id", severity="high"),
        RuleSpec(id="u:b", type="unique", column="order_id", severity="high"),
        RuleSpec(id="r:c", type="range", column="total_amount",
                 params={"min": 1000, "max": 2000}, severity="low"),
    ])
    outcome = _engine(clean_db).run(tables=["orders"], contract=contract)
    table = outcome.tables[0]
    # 2 high pass, 1 low fail -> (1.0+1.0)/(1.0+1.0+0.25) = 88.9 -> 89
    assert table.score == 89
    assert table.score_breakdown.severity["high"] == {"passed": 2, "failed": 0}
    assert table.score_breakdown.severity["low"] == {"passed": 0, "failed": 1}


def test_skips_excluded_from_score(clean_db):
    contract = _contract("orders", [
        RuleSpec(id="nn:a", type="not_null", column="order_id", severity="high"),
        RuleSpec(id="bad", type="freshness", column="order_id",
                 params={"max_age_hours": 1}, severity="high"),
    ])
    outcome = _engine(clean_db).run(tables=["orders"], contract=contract)
    table = outcome.tables[0]
    assert table.score == 100
    assert table.rule_results[1].status is RuleStatus.SKIP


# --- exit codes ------------------------------------------------------------


def test_exit_zero_when_clean(dirty_batch):
    contract = _contract("orders", [
        RuleSpec(id="nn:id", type="not_null", column="order_id", severity="high"),
    ])
    outcome = _engine(dirty_batch).run(
        tables=["orders"], contract=contract,
        policy=GatePolicy(max_failures=0, fail_on="low"),
    )
    assert decide_exit(outcome, GatePolicy()) == 0


def test_exit_one_on_gate_trip(dirty_batch):
    contract = _contract("orders", [
        RuleSpec(id="nn:user", type="not_null", column="user_id", severity="high"),
    ])
    policy = GatePolicy(max_failures=0, fail_on="low")
    outcome = _engine(dirty_batch).run(tables=["orders"], contract=contract,
                                       policy=policy)
    assert decide_exit(outcome, policy) == 1


def test_fail_on_threshold_respected(dirty_batch):
    contract = _contract("orders", [
        RuleSpec(id="r:amount", type="range", column="total_amount",
                 params={"min": 0, "max": 100}, severity="low"),
    ])
    low_policy = GatePolicy(max_failures=0, fail_on="low")
    high_policy = GatePolicy(max_failures=0, fail_on="high")
    outcome = _engine(dirty_batch).run(tables=["orders"], contract=contract,
                                       policy=low_policy)
    assert decide_exit(outcome, low_policy) == 1
    assert decide_exit(outcome, high_policy) == 0


def test_max_failures_tolerance(dirty_batch):
    contract = _contract("orders", [
        RuleSpec(id="r:amount", type="range", column="total_amount",
                 params={"min": 0, "max": 100}, severity="low"),
        RuleSpec(id="r:amount2", type="range", column="total_amount",
                 params={"min": 0, "max": 200}, severity="low"),
    ])
    policy = GatePolicy(max_failures=5, fail_on="high")
    outcome = _engine(dirty_batch).run(tables=["orders"], contract=contract,
                                       policy=policy)
    assert decide_exit(outcome, policy) == 0


def test_execution_error_wins_over_gate(dirty_batch):
    contract = _contract("orders", [
        RuleSpec(id="sql:boom", type="sql", column="*",
                 params={"query": "SELECT no_such_column FROM orders",
                         "expect": {"value": 0}}, severity="high"),
    ])
    policy = GatePolicy(max_failures=99, fail_on="high")
    outcome = _engine(dirty_batch).run(tables=["orders"], contract=contract,
                                       policy=policy)
    assert decide_exit(outcome, policy) == 2


# --- baseline --------------------------------------------------------------


def test_baseline_exempts_known_and_blocks_deterioration(dirty_batch):
    contract = _contract("orders", [
        RuleSpec(id="nn:user", type="not_null", column="user_id", severity="high"),
    ])
    engine = _engine(dirty_batch)
    outcome = engine.run(tables=["orders"], contract=contract)
    assert len(outcome.non_exempt_failures) == 1
    known = baseline_mod.capture(outcome, "2026-11-17T12:00:00+00:00")
    assert len(known.entries) == 1

    policy = GatePolicy(max_failures=0, fail_on="low")
    outcome2 = engine.run(tables=["orders"], contract=contract, baseline=known,
                          policy=policy)
    assert outcome2.non_exempt_failures == []
    assert outcome2.tables[0].rule_results[0].exempted is True
    assert decide_exit(outcome2, policy, known) == 0

    # deterioration: tighten the recorded count below the actual one
    known.entries[0].failed_count = 0
    outcome3 = engine.run(tables=["orders"], contract=contract, baseline=known,
                          policy=policy)
    assert len(outcome3.non_exempt_failures) == 1
    assert decide_exit(outcome3, policy, known) == 1


def test_baseline_never_exempts_errors(dirty_batch):
    contract = _contract("orders", [
        RuleSpec(id="sql:boom", type="sql", column="*",
                 params={"query": "SELECT nope FROM orders",
                         "expect": {"value": 0}}, severity="high"),
    ])
    engine = _engine(dirty_batch)
    outcome = engine.run(tables=["orders"], contract=contract)
    base = baseline_mod.capture(outcome, "now")
    assert base.entries == []
    outcome2 = engine.run(tables=["orders"], contract=contract, baseline=base)
    assert len(outcome2.rule_errors) == 1
    assert decide_exit(outcome2, GatePolicy()) == 2


# --- contract --------------------------------------------------------------


def test_contract_roundtrip_preserves_precision(clean_db, tmp_root):
    contract = _contract("orders", [
        RuleSpec(id="range:amount", type="range", column="total_amount",
                 params={"min": "0.01", "max": "123456789.99"}, severity="high"),
        RuleSpec(id="nn:id", type="not_null", column="order_id", severity="low",
                 enabled=False),
    ])
    path = save_contract(contract, tmp_root / "c.yml")
    loaded = load_contract(path)
    rules = loaded.specs_for("orders")
    assert rules[0].params["min"] == "0.01"
    assert rules[0].params["max"] == "123456789.99"
    assert rules[1].enabled is False


def test_contract_rejects_duplicate_ids(tmp_root):
    path = tmp_root / "dup.yml"
    path.write_text(
        "version: 1\ntables:\n  t:\n    rules:\n"
        "      - {id: a, type: not_null, column: x}\n"
        "      - {id: a, type: not_null, column: y}\n",
        encoding="utf-8",
    )
    from dqdoctor.contract import ContractError

    with pytest.raises(ContractError, match="duplicate rule id"):
        load_contract(path)


def test_contract_rejects_legacy_file_with_hint(tmp_root):
    path = tmp_root / "old.yml"
    path.write_text("table: t\nrules:\n  - rule_id: a\n    rule_type: not_null\n",
                    encoding="utf-8")
    from dqdoctor.contract import ContractError

    with pytest.raises(ContractError, match="legacy 0.7"):
        load_contract(path)


def test_contract_rejects_bad_version(tmp_root):
    path = tmp_root / "v2.yml"
    path.write_text("version: 2\ntables: {}\n", encoding="utf-8")
    from dqdoctor.contract import ContractError

    with pytest.raises(ContractError, match="Unsupported contract version"):
        load_contract(path)


def test_migrate_legacy_rules_file(tmp_root):
    from dqdoctor.contract import migrate_legacy

    legacy = tmp_root / "rules.yml"
    legacy.write_text(
        "table: orders\n"
        "rules:\n"
        "  - rule_id: not_null.user_id.3\n"
        "    rule_type: not_null\n"
        "    column: user_id\n"
        "    severity: high\n"
        "    enabled: true\n"
        "  - rule_id: range.amount.7\n"
        "    rule_type: range\n"
        "    column: amount\n"
        "    params: {min: 0, max: 100}\n"
        "    severity: low\n"
        "    enabled: false\n",
        encoding="utf-8",
    )
    contract = migrate_legacy(legacy)
    rules = contract.tables["orders"].rules
    assert len(rules) == 2
    # the 0.7 global counter suffix is stripped for stable ids
    assert rules[0].id == "not_null.user_id"
    assert rules[1].id == "range.amount"
    assert rules[1].enabled is False


def test_migrate_legacy_config_sql_rules(tmp_root):
    from dqdoctor.contract import migrate_legacy

    legacy = tmp_root / "cfg.yml"
    legacy.write_text(
        "db: demo.duckdb\n"
        "tables:\n"
        "  orders:\n"
        "    freshness:\n"
        "      created_at: {max_age_hours: 48}\n"
        "    sql_rules:\n"
        "      - name: positive\n"
        "        query: SELECT COUNT(*) FROM orders WHERE amount < 0\n"
        "        expect: 0\n",
        encoding="utf-8",
    )
    contract = migrate_legacy(legacy)
    rules = {r.id: r for r in contract.tables["orders"].rules}
    assert rules["freshness:created_at"].params["max_age_hours"] == 48
    assert rules["sql:positive"].params["expect"] == {"mode": "eq", "value": 0}
    assert contract.datasource == "demo.duckdb"


# --- sampling --------------------------------------------------------------


def test_sampled_profile_is_flagged_and_gating_still_full_scan(tmp_root):
    path = tmp_root / "big.duckdb"
    con = duckdb.connect(str(path))
    con.execute("CREATE TABLE b (v INTEGER)")
    con.execute("INSERT INTO b SELECT range FROM range(1000)")
    con.close()
    outcome = _engine(path).run(tables=["b"], explore=True, sample_rows=10)
    table = outcome.tables[0]
    assert table.profile.sampling.method == "sample"
    assert table.profile.sampling.sample_size == 10
    assert table.profile.sampling.row_count == 1000
    assert table.profile.sampling.coverage == pytest.approx(0.01)

    contract = _contract("b", [
        RuleSpec(id="rc:b", type="row_count", column="*",
                 params={"min": 900}, severity="high"),
    ])
    outcome2 = _engine(path).run(tables=["b"], contract=contract, sample_rows=10)
    # row_count reads the full row count even when profiling sampled
    assert outcome2.tables[0].profile.row_count == 1000
