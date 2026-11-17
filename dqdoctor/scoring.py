"""Quality scoring, version 1.0.

- Weighted by severity: high=1.0, medium=0.5, low=0.25. A failed rule
  contributes 0; skipped/suggestion/error rules stay out of the
  denominator (errors are visible in their own channel and gate exit
  codes, not the score).
- No executed checks => ``None`` (a table that ran nothing real has no
  quality score; 0.7 returned a misleading 100).
- PII is reported as independent findings and does not drag the score.
"""
from __future__ import annotations

from dqdoctor.models import RuleStatus, ScoreBreakdown, TableCheck

SCORE_VERSION = "1.0"
WEIGHTS = {"high": 1.0, "medium": 0.5, "low": 0.25}


def score_table(check: TableCheck) -> tuple[int | None, ScoreBreakdown]:
    executed = [
        r for r in check.rule_results if r.status in (RuleStatus.PASS, RuleStatus.FAIL)
    ]
    breakdown = ScoreBreakdown(executed_rules=len(executed))
    for r in executed:
        bucket = breakdown.severity.setdefault(
            r.severity, {"passed": 0, "failed": 0}
        )
        if r.status is RuleStatus.PASS:
            bucket["passed"] += 1
        else:
            bucket["failed"] += 1
    if not executed:
        return None, breakdown
    total_weight = sum(WEIGHTS[r.severity] for r in executed)
    passed_weight = sum(
        WEIGHTS[r.severity] for r in executed if r.status is RuleStatus.PASS
    )
    return int(round(100 * passed_weight / total_weight)), breakdown
