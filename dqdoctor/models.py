"""Result and contract models for dq-doctor 1.0.

Key 1.0 semantics:

- ``RuleStatus`` is explicit (``pass/fail/skip/suggestion/error``); nothing is
  inferred from counters. An empty table with a ``not_null`` rule that ran is a
  PASS, a custom SQL rule returning ``0`` is a real PASS, a rule with missing
  params is a SKIP, and an unvalidated learned boundary is a SUGGESTION.
- Rule IDs are stable and scoped (``{type}:{column}`` by default); two rules on
  the same column must carry explicit distinct IDs.
- Scores are optional: a table with no executed checks has ``score=None``.
- PII findings are evidence-backed and never carry raw sample values.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

Severity = Literal["high", "medium", "low"]


class RuleStatus(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    SKIP = "skip"
    SUGGESTION = "suggestion"
    ERROR = "error"


class RuleSpec(BaseModel):
    """A rule as stored in a contract or generated as a suggestion."""

    model_config = ConfigDict(extra="forbid")

    id: str
    type: str
    column: str = "*"
    params: dict[str, Any] = Field(default_factory=dict)
    severity: Severity = "medium"
    reason: str = ""
    source: str = "contract"  # contract | suggested | llm | builtin
    enabled: bool = True

    def key(self) -> tuple[str, str, str]:
        return (self.type, self.column, self.id)


class SamplingInfo(BaseModel):
    """How the profile numbers were obtained. Full scans are the default;
    explicit sampling must be visible and must not silently gate a table.
    """

    method: Literal["full", "sample"] = "full"
    sample_size: int = 0
    row_count: int = 0

    @property
    def coverage(self) -> float:
        if self.method == "full" or self.row_count == 0:
            return 1.0
        return self.sample_size / self.row_count


class ColumnProfile(BaseModel):
    name: str
    dtype: str
    null_count: int
    null_rate: float
    distinct_count: int
    distinct_rate: float
    min_value: Any = None
    max_value: Any = None
    # Raw samples live in memory only; reports/JSON redact them (see redact.py).
    sample_values: list[Any] = Field(default_factory=list, exclude=True)
    distinct_values: list[Any] = Field(default_factory=list, exclude=True)
    inferred_semantic_type: str = "unknown"
    pii_type: Optional[str] = None


class TableProfile(BaseModel):
    datasource: str  # redated display form, e.g. postgresql://u:***@h/db
    table_name: str
    row_count: int
    columns: list[ColumnProfile]
    sampling: SamplingInfo = Field(default_factory=SamplingInfo)
    profiled_at: str = Field(default_factory=lambda: datetime.now().isoformat())

    def column(self, name: str) -> ColumnProfile | None:
        return next((c for c in self.columns if c.name == name), None)


class PIIFinding(BaseModel):
    column: str
    pii_type: str
    matched_fraction: float
    sample_size: int


class RuleResult(BaseModel):
    rule_id: str
    rule_type: str
    column: str
    status: RuleStatus
    severity: Severity = "medium"
    failed_count: int = 0
    total_count: int = 0
    message: str = ""
    source: str = "contract"
    # Baseline bookkeeping (filled by engine when a baseline is active).
    exempted: bool = False
    exempt_reason: str = ""

    @property
    def executed(self) -> bool:
        return self.status in (RuleStatus.PASS, RuleStatus.FAIL)


class FKIssue(BaseModel):
    from_table: str
    from_column: str
    to_table: str
    to_column: str
    orphan_rows: int
    total_rows: int
    declared: bool = False  # True = DB-declared or user-configured, False = heuristic
    sample_orphans_redacted: int = 0  # count only; raw values stay out of reports
    error: str = ""

    @property
    def passed(self) -> bool:
        return self.orphan_rows == 0


class ScoreBreakdown(BaseModel):
    severity: dict[str, dict[str, int]] = Field(default_factory=dict)
    # e.g. {"high": {"passed": 2, "failed": 1}, ...}
    executed_rules: int = 0


class TableCheck(BaseModel):
    table_name: str
    profile: TableProfile
    rule_results: list[RuleResult] = Field(default_factory=list)
    pii_findings: list[PIIFinding] = Field(default_factory=list)
    fk_issues: list[FKIssue] = Field(default_factory=list)
    score: Optional[int] = None
    score_version: str = "1.0"
    score_breakdown: ScoreBreakdown = Field(default_factory=ScoreBreakdown)

    @property
    def failed(self) -> list[RuleResult]:
        return [r for r in self.rule_results if r.status is RuleStatus.FAIL]

    @property
    def errors(self) -> list[RuleResult]:
        return [r for r in self.rule_results if r.status is RuleStatus.ERROR]


class GatePolicy(BaseModel):
    """Quality gate configuration; the engine evaluates it once, centrally."""

    max_failures: int = 0
    fail_on: Severity = "low"  # any failure at >= this severity trips the gate
    baseline_active: bool = False


class CheckOutcome(BaseModel):
    schema_version: str = "1.0"
    dqdoctor_version: str = ""
    started_at: str = ""
    finished_at: str = ""
    datasource: str = ""  # redated display form
    tables: list[TableCheck] = Field(default_factory=list)
    fk_issues: list[FKIssue] = Field(default_factory=list)  # global, deduped
    gate_policy: Optional[GatePolicy] = None

    @property
    def rule_errors(self) -> list[RuleResult]:
        return [r for t in self.tables for r in t.errors]

    @property
    def non_exempt_failures(self) -> list[RuleResult]:
        return [
            r
            for t in self.tables
            for r in t.rule_results
            if r.status is RuleStatus.FAIL and not r.exempted
        ]


_SEVERITY_ORDER = {"low": 0, "medium": 1, "high": 2}


def severity_at_least(severity: str, threshold: str) -> bool:
    return _SEVERITY_ORDER[severity] >= _SEVERITY_ORDER[threshold]
