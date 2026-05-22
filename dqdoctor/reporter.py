from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from dqdoctor.models import (
    PIIFinding,
    ProfileResult,
    RefIntegrityIssue,
    ReportResult,
    RuleSuggestion,
    ValidationResult,
)

_TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"


def _compute_score(
    total: int,
    passed: int,
    failed: int,
    pii_count: int = 0,
    refint_issues: int = 0,
) -> int:
    if total == 0:
        base = 100
    else:
        base = int(passed / total * 100)
    pii_penalty = min(pii_count * 5, 20)
    refint_penalty = min(refint_issues * 10, 30)
    return max(0, base - pii_penalty - refint_penalty)


def build_report(
    profile: ProfileResult,
    rules: list[RuleSuggestion],
    results: list[ValidationResult],
    pii_findings: list[PIIFinding] | None = None,
    refint_issues: list[RefIntegrityIssue] | None = None,
) -> ReportResult:
    suggested = sum(1 for r in results if r.total_count == 0 and r.passed)
    validated = [r for r in results if not (r.total_count == 0 and r.passed)]
    passed = sum(1 for r in validated if r.passed)
    failed = len(validated) - passed
    total = passed + failed

    pii = pii_findings or []
    refint = refint_issues or []

    score = _compute_score(
        total, passed, failed,
        pii_count=len(pii),
        refint_issues=sum(1 for r in refint if r.orphan_rows > 0),
    )

    return ReportResult(
        db_path=profile.db_path,
        table_name=profile.table_name,
        row_count=profile.row_count,
        column_count=len(profile.columns),
        total_rules=len(rules),
        passed_rules=passed,
        failed_rules=failed,
        suggested_rules=suggested,
        quality_score=score,
        profile=profile,
        rules=rules,
        results=results,
        pii_findings=pii,
        referential_integrity=refint,
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
