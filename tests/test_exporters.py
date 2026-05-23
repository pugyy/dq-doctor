from pathlib import Path

import pytest

from dqdoctor.demo import create_demo_db
from dqdoctor.exporters.dbt import export_dbt_schema, save_dbt_schema
from dqdoctor.exporters.gx import export_gx_suite, save_gx_suite
from dqdoctor.exporters.markdown import export_markdown, save_markdown
from dqdoctor.profiler import profile_table
from dqdoctor.rule_engine import generate_rules


@pytest.fixture
def profile_and_rules(tmp_path: Path):
    db = create_demo_db(tmp_path / "test.duckdb")
    profile = profile_table(db, "orders")
    rules = generate_rules(profile)
    return profile, rules


def test_export_dbt_schema(profile_and_rules):
    profile, rules = profile_and_rules
    content = export_dbt_schema(profile, rules)
    assert "version: 2" in content
    assert "orders" in content
    assert "not_null" in content
    assert "order_id" in content


def test_dbt_range_includes_dbt_utils_note(profile_and_rules):
    profile, rules = profile_and_rules
    range_rules = [r for r in rules if r.rule_type == "range"]
    assert len(range_rules) > 0
    content = export_dbt_schema(profile, rules)
    assert "dbt-utils" in content
    assert "dbt_utils.expression_is_true" in content


def test_dbt_no_range_no_note(tmp_path: Path):
    from dqdoctor.exporters.dbt import export_dbt_schema
    from dqdoctor.models import ColumnProfile, ProfileResult, RuleSuggestion

    profile = ProfileResult(
        db_path="test.db",
        table_name="t",
        row_count=1,
        columns=[
            ColumnProfile(
                name="status",
                dtype="VARCHAR",
                null_count=0,
                null_rate=0.0,
                distinct_count=2,
                distinct_rate=1.0,
                inferred_semantic_type="category",
            )
        ],
    )
    rules = [
        RuleSuggestion(
            rule_id="not_null.status.1",
            rule_type="not_null",
            column="status",
            confidence=0.9,
            severity="high",
            reason="test",
        )
    ]
    content = export_dbt_schema(profile, rules)
    assert "dbt-utils" not in content
    assert "not_null" in content


def test_dbt_range_expression_includes_column_name(tmp_path: Path):
    from dqdoctor.exporters.dbt import export_dbt_schema
    from dqdoctor.models import ColumnProfile, ProfileResult, RuleSuggestion

    profile = ProfileResult(
        db_path="test.db",
        table_name="t",
        row_count=1,
        columns=[
            ColumnProfile(
                name="amount",
                dtype="DECIMAL",
                null_count=0,
                null_rate=0.0,
                distinct_count=5,
                distinct_rate=1.0,
                inferred_semantic_type="measure",
            )
        ],
    )
    rules = [
        RuleSuggestion(
            rule_id="range:amount.1",
            rule_type="range",
            column="amount",
            params={"min": 10, "max": 999},
            confidence=0.9,
            severity="medium",
            reason="test",
        )
    ]
    content = export_dbt_schema(profile, rules)
    assert "amount >= 10" in content
    assert "amount <= 999" in content


def test_save_dbt_schema(profile_and_rules, tmp_path: Path):
    profile, rules = profile_and_rules
    out = tmp_path / "schema.yml"
    saved = save_dbt_schema(profile, rules, out)
    assert saved.exists()
    content = saved.read_text(encoding="utf-8")
    assert "version: 2" in content


def test_export_gx_suite(profile_and_rules):
    profile, rules = profile_and_rules
    content = export_gx_suite(profile, rules)
    assert "expectation_suite_name" in content
    assert "expect_column_values_to_not_be_null" in content


def test_save_gx_suite(profile_and_rules, tmp_path: Path):
    profile, rules = profile_and_rules
    out = tmp_path / "suite.json"
    saved = save_gx_suite(profile, rules, out)
    assert saved.exists()
    content = saved.read_text(encoding="utf-8")
    assert "expectation_suite_name" in content


def test_export_markdown(profile_and_rules):
    profile, rules = profile_and_rules
    content = export_markdown(profile, rules)
    assert "# Data Dictionary: orders" in content
    assert "order_id" in content
    assert "## Quality Rules" in content


def test_save_markdown(profile_and_rules, tmp_path: Path):
    profile, rules = profile_and_rules
    out = tmp_path / "dict.md"
    saved = save_markdown(profile, rules, out)
    assert saved.exists()
    content = saved.read_text(encoding="utf-8")
    assert "order_id" in content
