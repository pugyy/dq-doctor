from pathlib import Path

import pytest

from dqdoctor.demo import create_demo_db
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
    assert report.passed_rules + report.failed_rules == len(results)


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
