from pathlib import Path

import pytest

from dqdoctor.demo import create_demo_db
from dqdoctor.profiler import profile_table
from dqdoctor.rule_engine import generate_rules
from dqdoctor.validator import validate_rules


@pytest.fixture
def demo_db(tmp_path: Path):
    return create_demo_db(tmp_path / "test.duckdb")


def test_validate_not_null_pass(demo_db: Path):
    profile = profile_table(demo_db, "orders")
    rules = generate_rules(profile)
    not_null_rules = [r for r in rules if r.rule_type == "not_null"]
    assert len(not_null_rules) > 0

    results = validate_rules(demo_db, "orders", not_null_rules)
    for result in results:
        assert result.rule_type == "not_null"
        assert result.passed is True


def test_validate_unique_pass(demo_db: Path):
    profile = profile_table(demo_db, "orders")
    rules = generate_rules(profile)
    unique_rules = [r for r in rules if r.rule_type == "unique"]
    assert len(unique_rules) > 0

    results = validate_rules(demo_db, "orders", unique_rules)
    for result in results:
        assert result.rule_type == "unique"
        assert result.passed is True


def test_validate_accepted_values(demo_db: Path):
    profile = profile_table(demo_db, "orders")
    rules = generate_rules(profile)
    av_rules = [r for r in rules if r.rule_type == "accepted_values"]

    if av_rules:
        results = validate_rules(demo_db, "orders", av_rules)
        for result in results:
            assert result.rule_type == "accepted_values"
            assert result.passed is True


def test_validate_range(demo_db: Path):
    profile = profile_table(demo_db, "orders")
    rules = generate_rules(profile)
    range_rules = [r for r in rules if r.rule_type == "range"]
    assert len(range_rules) > 0

    results = validate_rules(demo_db, "orders", range_rules)
    for result in results:
        assert result.rule_type == "range"
        assert result.passed is True


def test_validate_freshness_passes_with_recent_data(demo_db: Path):
    profile = profile_table(demo_db, "orders")
    rules = generate_rules(profile)
    freshness_rules = [r for r in rules if r.rule_type == "freshness"]
    assert len(freshness_rules) > 0

    results = validate_rules(demo_db, "orders", freshness_rules)
    for result in results:
        assert result.passed is True


def test_validate_all_rules(demo_db: Path):
    profile = profile_table(demo_db, "orders")
    rules = generate_rules(profile)
    results = validate_rules(demo_db, "orders", rules)

    assert len(results) == len(rules)
    for result in results:
        assert result.rule_id is not None
        assert result.passed in (True, False)
        assert result.total_count >= 0


def test_validate_users_with_nulls(tmp_path: Path):
    db = create_demo_db(tmp_path / "test.duckdb")
    profile = profile_table(db, "users")
    rules = generate_rules(profile)
    results = validate_rules(db, "users", rules)

    email_not_null = next(
        (r for r in results if r.column == "email" and r.rule_type == "not_null"),
        None,
    )
    if email_not_null:
        assert email_not_null.passed is False
        assert email_not_null.failed_count > 0
