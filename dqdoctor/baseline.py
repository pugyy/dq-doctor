"""Known-failure baselines for onboarding legacy systems.

A baseline records the failures that were accepted at capture time. At
check time, a failing rule is exempted only when the *same* rule on the
*same* table fails with **no worse** counts - a new failure on the same
rule, or a deteriorating count, still trips the gate. Execution errors
are never exempted.
"""
from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

from pydantic import BaseModel, Field

from dqdoctor.models import CheckOutcome, FKIssue, RuleSpec, RuleStatus


class BaselineEntry(BaseModel):
    table: str
    rule_id: str
    rule_type: str
    column: str
    failed_count: int
    definition_hash: str


class FKBaselineEntry(BaseModel):
    key: tuple[str, str, str, str]
    orphan_rows: int


class Baseline(BaseModel):
    version: int = 2
    captured_at: str = ""
    entries: list[BaselineEntry] = Field(default_factory=list)
    fk_entries: list[FKBaselineEntry] = Field(default_factory=list)


def definition_hash(spec: RuleSpec) -> str:
    definition = spec.model_dump(mode="json", include={"type", "column", "params", "severity"})
    return sha256(json.dumps(definition, sort_keys=True).encode()).hexdigest()


def capture(outcome: CheckOutcome, captured_at: str) -> Baseline:
    """Record current failures (and failing FK pairs) as the new baseline."""
    entries = []
    for table in outcome.tables:
        for r in table.rule_results:
            if r.status is RuleStatus.FAIL and not r.exempted and r.definition_hash:
                entries.append(
                    BaselineEntry(
                        table=table.table_name,
                        rule_id=r.rule_id,
                        rule_type=r.rule_type,
                        column=r.column,
                        failed_count=max(r.failed_count, 1),
                        definition_hash=r.definition_hash,
                    )
                )
    fk_entries = [
        FKBaselineEntry(key=_fk_key(fk), orphan_rows=fk.orphan_rows)
        for fk in outcome.fk_issues
        if fk.orphan_rows > 0 and not fk.error
    ]
    return Baseline(captured_at=captured_at, entries=entries, fk_entries=fk_entries)


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
    if isinstance(data, dict) and data.get("version") != 2:
        raise ValueError("Unsupported baseline version. Re-create it with baseline capture.")
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
            if entry is None or entry.definition_hash != r.definition_hash:
                continue
            if r.failed_count <= entry.failed_count:
                r.exempted = True
                r.exempt_reason = (
                    f"known failure (baseline: <= {entry.failed_count})"
                )
            # else: deterioration -> stays a gating failure

def fk_is_exempt(fk: FKIssue, baseline: Baseline) -> bool:
    return not fk.error and any(
        entry.key == _fk_key(fk) and fk.orphan_rows <= entry.orphan_rows
        for entry in baseline.fk_entries
    )


def _fk_key(fk: FKIssue) -> tuple[str, str, str, str]:
    return (fk.from_table, fk.from_column, fk.to_table, fk.to_column)
