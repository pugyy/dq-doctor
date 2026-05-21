from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from dqdoctor.models import (
    ProfileResult,
    ReportResult,
    RuleSuggestion,
    ValidationResult,
)

_TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"


def build_report(
    profile: ProfileResult,
    rules: list[RuleSuggestion],
    results: list[ValidationResult],
) -> ReportResult:
    suggested = sum(1 for r in results if r.total_count == 0 and r.passed)
    validated = [r for r in results if not (r.total_count == 0 and r.passed)]
    passed = sum(1 for r in validated if r.passed)
    failed = len(validated) - passed
    return ReportResult(
        db_path=profile.db_path,
        table_name=profile.table_name,
        row_count=profile.row_count,
        column_count=len(profile.columns),
        total_rules=len(rules),
        passed_rules=passed,
        failed_rules=failed,
        suggested_rules=suggested,
        profile=profile,
        rules=rules,
        results=results,
    )


def render_html(report: ReportResult) -> str:
    env = Environment(loader=FileSystemLoader(str(_TEMPLATE_DIR)), autoescape=True)
    template = env.get_template("report.html")
    return template.render(report=report)


def save_html(report: ReportResult, output_path: "str | Path") -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    html = render_html(report)
    output_path.write_text(html, encoding="utf-8")
    return output_path
