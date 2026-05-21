from pathlib import Path

import pytest

from dqdoctor.demo import create_demo_db
from dqdoctor.models import RuleSuggestion
from dqdoctor.profiler import profile_table
from dqdoctor.reporter import build_report, render_html, save_html
from dqdoctor.rule_engine import generate_rules
from dqdoctor.validator import validate_rules


@pytest.fixture
def demo_report_data(tmp_path: Path):
    db = create_demo_db(tmp_path / "test.duckdb")
    profile = profile_table(db, "orders")
    rules = generate_rules(profile)
    results = validate_rules(db, "orders", rules)
    return profile, rules, results


def test_build_report(demo_report_data):
    profile, rules, results = demo_report_data
    report = build_report(profile, rules, results)

    assert report.table_name == "orders"
    assert report.row_count == 20
    assert report.column_count == len(profile.columns)
    assert report.total_rules == len(rules)
    assert report.passed_rules + report.failed_rules + report.suggested_rules == len(results)


def test_suggested_rules_counted_separately(tmp_path: Path):
    db = create_demo_db(tmp_path / "test.duckdb")
    profile = profile_table(db, "orders")
    rules = generate_rules(profile)
    llm_rule = RuleSuggestion(
        rule_id="llm.test.0",
        rule_type="business_rule",
        column="status",
        params={},
        confidence=0.6,
        severity="medium",
        reason="Status should follow lifecycle order",
        source="llm",
    )
    rules_with_llm = rules + [llm_rule]
    results = validate_rules(db, "orders", rules_with_llm)
    report = build_report(profile, rules_with_llm, results)

    assert report.suggested_rules >= 1
    llm_result = next(r for r in results if r.rule_id == "llm.test.0")
    assert llm_result.total_count == 0
    assert llm_result.passed is True
    assert report.passed_rules + report.failed_rules == len(results) - report.suggested_rules


def test_render_html(demo_report_data):
    profile, rules, results = demo_report_data
    report = build_report(profile, rules, results)
    html = render_html(report)

    assert "<html" in html
    assert "orders" in html
    assert "PASS" in html or "FAIL" in html
    for rule in rules:
        assert rule.rule_type in html


def test_save_html(demo_report_data, tmp_path: Path):
    profile, rules, results = demo_report_data
    report = build_report(profile, rules, results)
    output = tmp_path / "output" / "report.html"
    saved = save_html(report, output)

    assert saved.exists()
    content = saved.read_text(encoding="utf-8")
    assert "<html" in content
    assert "orders" in content
