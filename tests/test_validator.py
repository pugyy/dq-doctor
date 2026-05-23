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


def test_validate_freshness_with_date_column(tmp_path: Path):
    import duckdb
    from dqdoctor.models import RuleSuggestion

    db_path = tmp_path / "date_test.duckdb"
    con = duckdb.connect(str(db_path))
    con.execute("CREATE TABLE events (event_id INT, event_date DATE)")
    con.execute(
        "INSERT INTO events VALUES (1, CURRENT_DATE), (2, CURRENT_DATE - INTERVAL 1 DAY)"
    )
    con.close()

    rule = RuleSuggestion(
        rule_id="freshness:event_date",
        rule_type="freshness",
        column="event_date",
        params={"max_age_hours": 48},
        confidence=1.0,
        severity="medium",
        reason="test",
        source="heuristic",
    )

    results = validate_rules(db_path, "events", [rule])
    assert len(results) == 1
    assert results[0].passed is True
