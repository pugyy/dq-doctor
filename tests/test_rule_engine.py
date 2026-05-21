from pathlib import Path

import pytest

from dqdoctor.demo import create_demo_db
from dqdoctor.profiler import profile_table
from dqdoctor.rule_engine import generate_rules


@pytest.fixture
def demo_db(tmp_path: Path):
    return create_demo_db(tmp_path / "test.duckdb")


def test_generate_rules_orders(demo_db: Path):
    profile = profile_table(demo_db, "orders")
    rules = generate_rules(profile)
    assert len(rules) > 0

    rule_types = [r.rule_type for r in rules]
    assert "not_null" in rule_types
    assert "unique" in rule_types
    assert "range" in rule_types


def test_not_null_for_identifiers(demo_db: Path):
    profile = profile_table(demo_db, "orders")
    rules = generate_rules(profile)
    order_id_rules = [r for r in rules if r.column == "order_id"]
    not_null_rule = next(
        (r for r in order_id_rules if r.rule_type == "not_null"), None,
    )
    assert not_null_rule is not None
    assert not_null_rule.severity == "high"
    assert (
        "identifier" in not_null_rule.reason.lower()
        or "zero null" in not_null_rule.reason.lower()
    )


def test_unique_for_identifiers(demo_db: Path):
    profile = profile_table(demo_db, "orders")
    rules = generate_rules(profile)
    unique_rule = next(
        (r for r in rules if r.column == "order_id" and r.rule_type == "unique"),
        None,
    )
    assert unique_rule is not None
    assert unique_rule.confidence >= 0.8


def test_unique_not_generated_for_measures(demo_db: Path):
    profile = profile_table(demo_db, "orders")
    rules = generate_rules(profile)
    amount_unique = [
        r for r in rules
        if r.column == "total_amount" and r.rule_type == "unique"
    ]
    assert len(amount_unique) == 0


def test_accepted_values_for_categories(demo_db: Path):
    profile = profile_table(demo_db, "orders")
    rules = generate_rules(profile)
    status_rule = next(
        (r for r in rules if r.column == "status"
         and r.rule_type == "accepted_values"),
        None,
    )
    assert status_rule is not None
    assert "values" in status_rule.params
    values = status_rule.params["values"]
    assert len(values) > 0
    profile_col = next(c for c in profile.columns if c.name == "status")
    assert len(values) == profile_col.distinct_count


def test_range_for_numeric(demo_db: Path):
    profile = profile_table(demo_db, "orders")
    rules = generate_rules(profile)
    range_rules = [r for r in rules if r.rule_type == "range"]
    assert len(range_rules) > 0
    for r in range_rules:
        assert "min" in r.params
        assert "max" in r.params


def test_range_includes_decimal(demo_db: Path):
    profile = profile_table(demo_db, "orders")
    rules = generate_rules(profile)
    amount_range = next(
        (r for r in rules if r.column == "total_amount" and r.rule_type == "range"),
        None,
    )
    assert amount_range is not None


def test_freshness_for_timestamps(demo_db: Path):
    profile = profile_table(demo_db, "orders")
    rules = generate_rules(profile)
    freshness_rules = [r for r in rules if r.rule_type == "freshness"]
    assert len(freshness_rules) > 0
    for r in freshness_rules:
        assert r.params.get("max_age_hours") == 24


def test_all_rules_have_reason(demo_db: Path):
    profile = profile_table(demo_db, "orders")
    rules = generate_rules(profile)
    for rule in rules:
        assert len(rule.reason) > 0


def test_all_rules_have_source(demo_db: Path):
    profile = profile_table(demo_db, "orders")
    rules = generate_rules(profile)
    for rule in rules:
        assert rule.source == "heuristic"
