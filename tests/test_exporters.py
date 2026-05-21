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
