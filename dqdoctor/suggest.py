"""Suggestion generation for the zero-config explore mode.

Learned boundaries and accepted sets are **suggestions**, never executed
rules: explore mode honestly labels everything it induced from the current
batch as a suggestion and leaves execution to a pinned contract. That is
the 1.0 fix for 0.7's self-validating loop (range from observed min/max
"passed" trivially).
"""
from __future__ import annotations

from dqdoctor.models import ColumnProfile, RuleSpec, TableProfile
from dqdoctor.profiling import is_numeric, is_temporal


def suggest_for_table(profile: TableProfile) -> list[RuleSpec]:
    specs: list[RuleSpec] = []
    for col in profile.columns:
        specs.extend(_suggest_column(profile, col))
    return specs


def table_scoped(rule: RuleSpec, table: str) -> RuleSpec:
    """Rule ids are unique across a contract: scope them to the table.

    The contract holds every table, so ``not_null:user_id`` would collide
    between tables. Ids are rewritten as ``table/type:column`` once, when
    the contract is assembled.
    """
    return rule.model_copy(update={"id": f"{table}/{rule.id}"})


def _suggest_column(profile: TableProfile, col: ColumnProfile) -> list[RuleSpec]:
    out: list[RuleSpec] = []
    name = col.name
    if col.null_rate == 0 or col.inferred_semantic_type == "identifier":
        out.append(
            RuleSpec(
                id=f"not_null:{name}", type="not_null", column=name,
                severity="high" if col.inferred_semantic_type == "identifier"
                else "medium",
                reason=(
                    f"'{name}' has zero nulls across {profile.row_count} rows"
                    if col.null_rate == 0
                    else f"'{name}' looks like an identifier"
                ),
                source="suggested",
            )
        )
    if (
        col.inferred_semantic_type == "identifier"
        and profile.row_count - col.null_count > 0
        and col.distinct_rate >= 0.98
    ):
        out.append(
            RuleSpec(
                id=f"unique:{name}", type="unique", column=name, severity="high",
                reason=(f"'{name}' is an identifier with "
                        f"{col.distinct_rate:.1%} distinct rate"),
                source="suggested",
            )
        )
    if (
        col.inferred_semantic_type == "category"
        and 0 < col.distinct_count <= 20
        and col.distinct_values
    ):
        out.append(
            RuleSpec(
                id=f"accepted_values:{name}", type="accepted_values", column=name,
                params={"values": [str(v) for v in col.distinct_values]},
                severity="medium",
                reason=(f"'{name}' is categorical with {col.distinct_count} "
                        f"distinct values"),
                source="suggested",
            )
        )
    if is_numeric(col.dtype) and col.min_value is not None and col.max_value is not None:
        out.append(
            RuleSpec(
                id=f"range:{name}", type="range", column=name,
                params={"min": str(col.min_value), "max": str(col.max_value)},
                severity="low",
                reason=(f"'{name}' is numeric; observed [{col.min_value}, "
                        f"{col.max_value}] on the reference batch"),
                source="suggested",
            )
        )
    if col.inferred_semantic_type == "event_time" and is_temporal(col.dtype):
        out.append(
            RuleSpec(
                id=f"freshness:{name}", type="freshness", column=name,
                params={"max_age_hours": 24}, severity="high",
                reason=f"'{name}' is an event-time TIMESTAMP/DATE column",
                source="suggested",
            )
        )
    return out
