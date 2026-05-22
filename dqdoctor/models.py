from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class ColumnProfile(BaseModel):
    name: str
    dtype: str
    null_count: int
    null_rate: float
    distinct_count: int
    distinct_rate: float
    min_value: Any = None
    max_value: Any = None
    sample_values: list[Any] = Field(default_factory=list)
    distinct_values: list[Any] = Field(default_factory=list)
    inferred_semantic_type: str = "unknown"
    pii_type: Optional[str] = None


class ProfileResult(BaseModel):
    db_path: str
    table_name: str
    row_count: int
    columns: list[ColumnProfile]
    profiled_at: str = Field(default_factory=lambda: datetime.now().isoformat())


class RuleSuggestion(BaseModel):
    rule_id: str
    rule_type: str
    column: str
    params: dict[str, Any] = Field(default_factory=dict)
    confidence: float = 0.0
    severity: str = "medium"
    reason: str = ""
    source: str = "heuristic"


class ValidationResult(BaseModel):
    rule_id: str
    rule_type: str
    column: str
    passed: bool
    failed_count: int
    total_count: int
    message: str = ""


class PIIFinding(BaseModel):
    column: str
    pii_type: str
    sample_count: int = 0


class RefIntegrityIssue(BaseModel):
    from_table: str
    from_column: str
    to_table: str
    to_column: str
    orphan_rows: int
    total_rows: int
    sample_orphans: list = []


class ReportResult(BaseModel):
    db_path: str
    table_name: str
    row_count: int
    column_count: int
    total_rules: int
    passed_rules: int
    failed_rules: int
    suggested_rules: int = 0
    quality_score: int = 100
    profile: ProfileResult
    rules: list[RuleSuggestion]
    results: list[ValidationResult]
    pii_findings: list[PIIFinding] = []
    referential_integrity: list[RefIntegrityIssue] = []
    generated_at: str = Field(default_factory=lambda: datetime.now().isoformat())
