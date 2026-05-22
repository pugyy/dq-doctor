from __future__ import annotations

from pathlib import Path

import pytest

from dqdoctor.config import (
    DQConfig,
    TableConfig,
    apply_config_to_rules,
    get_sql_rules,
    load_config,
)
from dqdoctor.demo import create_demo_db, create_dirty_db
from dqdoctor.models import RuleSuggestion
from dqdoctor.ref_integrity import check_referential_integrity
from dqdoctor.sql_rules import execute_sql_rules


@pytest.fixture
def demo_db(tmp_path: Path):
    return create_demo_db(tmp_path / "test.duckdb")


@pytest.fixture
def dirty_db(tmp_path: Path):
    return create_dirty_db(tmp_path / "dirty.duckdb")


# --- Config ---

def test_load_config_missing_file():
    config = load_config("/nonexistent/.dqdoctor.yml")
    assert config.db is None
    assert config.tables == {}


def test_load_config_from_file(tmp_path: Path):
    cfg = tmp_path / ".dqdoctor.yml"
    cfg.write_text(
        "db: test.db\n"
        "tables:\n"
        "  orders:\n"
        "    disable_rules:\n"
        "      - range:user_id\n"
        "    severity:\n"
        "      order_id:not_null: high\n"
        "    sql_rules:\n"
        "      - name: positive_amount\n"
        "        query: 'SELECT COUNT(*) FROM orders WHERE total_amount <= 0'\n"
        "        expect: 0\n",
        encoding="utf-8",
    )
    config = load_config(cfg)
    assert config.db == "test.db"
    assert "orders" in config.tables
    assert "range:user_id" in config.tables["orders"].disable_rules
    assert config.tables["orders"].severity["order_id:not_null"] == "high"
    assert len(config.tables["orders"].sql_rules) == 1


def test_apply_config_disable_rules():
    rules = [
        RuleSuggestion(
            rule_id="range.user_id.1",
            rule_type="range",
            column="user_id",
            confidence=0.7,
            severity="low",
            reason="test",
        ),
        RuleSuggestion(
            rule_id="not_null.order_id.2",
            rule_type="not_null",
            column="order_id",
            confidence=0.9,
            severity="high",
            reason="test",
        ),
    ]
    config = DQConfig(tables={"orders": TableConfig(disable_rules=["range:user_id"])})
    result, log = apply_config_to_rules(rules, "orders", config)
    assert len(result) == 1
    assert result[0].rule_type == "not_null"


def test_apply_config_override_severity():
    rules = [
        RuleSuggestion(
            rule_id="not_null.order_id.1",
            rule_type="not_null",
            column="order_id",
            confidence=0.9,
            severity="medium",
            reason="test",
        ),
    ]
    config = DQConfig(tables={
        "orders": TableConfig(severity={"order_id:not_null": "high"})
    })
    result, log = apply_config_to_rules(rules, "orders", config)
    assert result[0].severity == "high"


def test_get_sql_rules():
    config = DQConfig(tables={
        "orders": TableConfig(sql_rules=[
            {"name": "test", "query": "SELECT 1", "expect": 1}
        ])
    })
    sql_rules = get_sql_rules(config, "orders")
    assert len(sql_rules) == 1
    assert sql_rules[0]["name"] == "test"


def test_get_sql_rules_no_table():
    config = DQConfig()
    assert get_sql_rules(config, "orders") == []


# --- SQL Rules ---

def test_execute_sql_rules(demo_db: Path):
    sql_rules = [
        {
            "name": "positive_amount",
            "query": "SELECT COUNT(*) FROM orders WHERE total_amount <= 0",
            "expect": 0,
        },
    ]
    results = execute_sql_rules(str(demo_db), "orders", sql_rules)
    assert len(results) == 1
    assert results[0].passed is True
    assert results[0].rule_type == "sql"


def test_execute_sql_rules_dirty(dirty_db: Path):
    sql_rules = [
        {
            "name": "positive_amount",
            "query": (
                "SELECT COUNT(*) FROM dirty_orders WHERE total_amount <= 0"
            ),
            "expect": 0,
        },
    ]
    results = execute_sql_rules(str(dirty_db), "dirty_orders", sql_rules)
    assert len(results) == 1
    assert results[0].passed is False


def test_execute_sql_rules_empty():
    results = execute_sql_rules("test.db", "orders", [])
    assert results == []


# --- Referential Integrity ---

def test_ref_integrity_clean(demo_db: Path):
    results = check_referential_integrity(demo_db)
    assert len(results) > 0
    for r in results:
        assert r.passed is True
        assert r.orphan_rows == 0


def test_ref_integrity_dirty(dirty_db: Path):
    results = check_referential_integrity(dirty_db)
    orphan_results = [r for r in results if not r.passed]
    assert len(orphan_results) > 0
    for r in orphan_results:
        assert r.orphan_rows > 0
        assert len(r.sample_orphans) > 0


# --- Dirty Demo ---

def test_dirty_db_created(dirty_db: Path):
    assert dirty_db.exists()


def test_dirty_db_tables(dirty_db: Path):
    from dqdoctor.demo import list_tables
    tables = list_tables(dirty_db)
    assert "dirty_orders" in tables
    assert "dirty_users" in tables


def test_dirty_db_has_nulls(dirty_db: Path):
    from dqdoctor.profiler import profile_table
    profile = profile_table(dirty_db, "dirty_orders")
    user_id = next(c for c in profile.columns if c.name == "user_id")
    assert user_id.null_count > 0


def test_dirty_db_has_orphan_fk(dirty_db: Path):
    from dqdoctor.profiler import profile_table
    profile = profile_table(dirty_db, "dirty_orders")
    user_id = next(c for c in profile.columns if c.name == "user_id")
    assert user_id.max_value == 99
