from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel

from dqdoctor.models import ProfileResult


class ColumnDrift(BaseModel):
    column: str
    metric: str
    old_value: Any
    new_value: Any
    change: str
    severity: str


class DriftResult(BaseModel):
    old_profile: str
    new_profile: str
    table_name: str
    drifts: list[ColumnDrift]
    summary: str


def save_profile(profile: ProfileResult, path: "str | Path") -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(profile.model_dump_json(indent=2), encoding="utf-8")
    return path


def load_profile(path: "str | Path") -> ProfileResult:
    path = Path(path)
    content = path.read_text(encoding="utf-8")
    return ProfileResult.model_validate_json(content)


def compare_profiles(
    old: ProfileResult,
    new: ProfileResult,
    null_rate_threshold: float = 0.05,
    distinct_rate_threshold: float = 0.1,
    row_count_threshold: float = 0.2,
) -> DriftResult:
    drifts: list[ColumnDrift] = []

    if old.table_name != new.table_name:
        return DriftResult(
            old_profile=old.db_path,
            new_profile=new.db_path,
            table_name=f"{old.table_name} vs {new.table_name}",
            drifts=[],
            summary="Tables differ, cannot compare.",
        )

    if abs(new.row_count - old.row_count) / max(old.row_count, 1) > row_count_threshold:
        drifts.append(
            ColumnDrift(
                column="*",
                metric="row_count",
                old_value=old.row_count,
                new_value=new.row_count,
                change=f"rows changed from {old.row_count} to {new.row_count}",
                severity="high",
            )
        )

    old_cols = {c.name: c for c in old.columns}
    new_cols = {c.name: c for c in new.columns}

    for name in set(old_cols) | set(new_cols):
        if name not in new_cols:
            drifts.append(
                ColumnDrift(
                    column=name,
                    metric="existence",
                    old_value="present",
                    new_value="missing",
                    change=f"column '{name}' was removed",
                    severity="high",
                )
            )
            continue
        if name not in old_cols:
            drifts.append(
                ColumnDrift(
                    column=name,
                    metric="existence",
                    old_value="missing",
                    new_value="present",
                    change=f"column '{name}' was added",
                    severity="low",
                )
            )
            continue

        oc = old_cols[name]
        nc = new_cols[name]

        if abs(nc.null_rate - oc.null_rate) > null_rate_threshold:
            drifts.append(
                ColumnDrift(
                    column=name,
                    metric="null_rate",
                    old_value=round(oc.null_rate, 4),
                    new_value=round(nc.null_rate, 4),
                    change=f"null rate changed from {oc.null_rate:.2%} to {nc.null_rate:.2%}",
                    severity="high" if nc.null_rate > oc.null_rate else "low",
                )
            )

        if abs(nc.distinct_rate - oc.distinct_rate) > distinct_rate_threshold:
            drifts.append(
                ColumnDrift(
                    column=name,
                    metric="distinct_rate",
                    old_value=round(oc.distinct_rate, 4),
                    new_value=round(nc.distinct_rate, 4),
                    change=(
                        f"distinct rate changed from "
                        f"{oc.distinct_rate:.2%} to {nc.distinct_rate:.2%}"
                    ),
                    severity="medium",
                )
            )

        if oc.dtype != nc.dtype:
            drifts.append(
                ColumnDrift(
                    column=name,
                    metric="dtype",
                    old_value=oc.dtype,
                    new_value=nc.dtype,
                    change=f"type changed from {oc.dtype} to {nc.dtype}",
                    severity="high",
                )
            )

    high = sum(1 for d in drifts if d.severity == "high")
    medium = sum(1 for d in drifts if d.severity == "medium")
    low = sum(1 for d in drifts if d.severity == "low")
    summary = f"Found {len(drifts)} drift(s): {high} high, {medium} medium, {low} low"

    return DriftResult(
        old_profile=old.db_path,
        new_profile=new.db_path,
        table_name=old.table_name,
        drifts=drifts,
        summary=summary,
    )
