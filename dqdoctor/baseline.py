"""Known-failure baselines for onboarding legacy systems.

A baseline records the failures that were accepted at capture time. At
check time, a failing rule is exempted only when the *same* rule on the
*same* table fails with **no worse** counts - a new failure on the same
rule, or a deteriorating count, still trips the gate. Execution errors
are never exempted.
"""
from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field

from dqdoctor.models import CheckOutcome, FKIssue, RuleStatus


class BaselineEntry(BaseModel):
    table: str
    rule_id: str
    rule_type: str
    column: str
    failed_count: int
    message_hint: str = ""  # stable prefix of the failure message


class Baseline(BaseModel):
    version: int = 1
    captured_at: str = ""
    entries: list[BaselineEntry] = Field(default_factory=list)
    fk_pairs: list[list[str]] = Field(default_factory=list)  # [from_t, from_c, to_t, to_c]


def capture(outcome: CheckOutcome, captured_at: str) -> Baseline:
    """Record current failures (and failing FK pairs) as the new baseline."""
    entries = []
    for table in outcome.tables:
        for r in table.rule_results:
            if r.status is RuleStatus.FAIL and not r.exempted:
                entries.append(
                    BaselineEntry(
                        table=table.table_name,
                        rule_id=r.rule_id,
                        rule_type=r.rule_type,
                        column=r.column,
                        failed_count=max(r.failed_count, 1),
                        message_hint=_hint(r.message),
                    )
                )
    fk_pairs = [
        [fk.from_table, fk.from_column, fk.to_table, fk.to_column]
        for fk in outcome.fk_issues
        if fk.orphan_rows > 0
    ]
    return Baseline(version=1, captured_at=captured_at, entries=entries,
                    fk_pairs=fk_pairs)


def _hint(message: str) -> str:
    return message[:60]


def save_baseline(baseline: Baseline, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(baseline.model_dump(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return path


def load_baseline(path: Path) -> Baseline:
    if not path.exists():
        raise FileNotFoundError(f"Baseline file not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    return Baseline.model_validate(data)


def apply_baseline(outcome: CheckOutcome, baseline: Baseline) -> None:
    """Mark matching failures as exempted, in place.

    Matching = same table + rule identity + failed_count <= baseline count.
    Errors never match. Non-exempted failures keep gating.
    """
    index: dict[tuple[str, str], BaselineEntry] = {}
    for entry in baseline.entries:
        index[(entry.table, entry.rule_id)] = entry

    for table in outcome.tables:
        for r in table.rule_results:
            if r.status is not RuleStatus.FAIL:
                continue
            entry = index.get((table.table_name, r.rule_id))
            if entry is None:
                continue
            if r.failed_count <= entry.failed_count:
                r.exempted = True
                r.exempt_reason = (
                    f"known failure (baseline: <= {entry.failed_count})"
                )
            # else: deterioration -> stays a gating failure

    base_fk = {tuple(pair) for pair in baseline.fk_pairs}
    _ = base_fk  # FK exemptions are evaluated via fk_is_exempt() at gate time


def fk_is_exempt(fk: FKIssue, baseline: Baseline) -> bool:
    return _fk_key(fk) in {tuple(pair) for pair in baseline.fk_pairs}


def _fk_key(fk: FKIssue) -> tuple[str, str, str, str]:
    return (fk.from_table, fk.from_column, fk.to_table, fk.to_column)
