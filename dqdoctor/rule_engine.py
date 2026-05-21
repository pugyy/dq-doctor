from __future__ import annotations

from typing import Optional

from dqdoctor.models import ColumnProfile, ProfileResult, RuleSuggestion

_RULE_ID_COUNTER = 0


def _next_rule_id(rule_type: str, column: str) -> str:
    global _RULE_ID_COUNTER
    _RULE_ID_COUNTER += 1
    return f"{rule_type}.{column}.{_RULE_ID_COUNTER}"


def _generate_not_null(col: ColumnProfile) -> RuleSuggestion | None:
    if col.null_rate == 0:
        return RuleSuggestion(
            rule_id=_next_rule_id("not_null", col.name),
            rule_type="not_null",
            column=col.name,
            confidence=0.9,
            severity="high" if col.inferred_semantic_type == "identifier" else "medium",
            reason=f"Column '{col.name}' has zero nulls across all rows, likely a required field.",
            source="heuristic",
        )
    if col.inferred_semantic_type == "identifier":
        return RuleSuggestion(
            rule_id=_next_rule_id("not_null", col.name),
            rule_type="not_null",
            column=col.name,
            confidence=0.8,
            severity="high",
            reason=f"Column '{col.name}' is inferred as an identifier and should not be null.",
            source="heuristic",
        )
    return None


def _generate_unique(col: ColumnProfile) -> RuleSuggestion | None:
    if col.inferred_semantic_type == "identifier" and col.distinct_rate >= 0.98:
        return RuleSuggestion(
            rule_id=_next_rule_id("unique", col.name),
            rule_type="unique",
            column=col.name,
            confidence=0.85,
            severity="high",
            reason=(
                f"Column '{col.name}' is an identifier with "
                f"{col.distinct_rate:.1%} distinct rate, likely unique."
            ),
            source="heuristic",
        )
    return None


def _generate_accepted_values(col: ColumnProfile) -> RuleSuggestion | None:
    if (
        col.inferred_semantic_type == "category"
        and col.distinct_count <= 20
        and len(col.distinct_values) > 0
    ):
        return RuleSuggestion(
            rule_id=_next_rule_id("accepted_values", col.name),
            rule_type="accepted_values",
            column=col.name,
            params={"values": col.distinct_values},
            confidence=0.8,
            severity="medium",
            reason=(
                f"Column '{col.name}' is a category field with only "
                f"{col.distinct_count} distinct values."
            ),
            source="heuristic",
        )
    return None


_NUMERIC_DTYPES = {
    "TINYINT", "SMALLINT", "INTEGER", "BIGINT",
    "UTINYINT", "USMALLINT", "UINTEGER", "UBIGINT",
    "FLOAT", "DOUBLE", "DECIMAL", "HUGEINT",
}


def _is_numeric_dtype(dtype: str) -> bool:
    upper = dtype.upper()
    return upper in _NUMERIC_DTYPES or upper.startswith("DECIMAL")


def _generate_range(col: ColumnProfile) -> RuleSuggestion | None:
    if not _is_numeric_dtype(col.dtype):
        return None
    if col.min_value is None or col.max_value is None:
        return None
    return RuleSuggestion(
        rule_id=_next_rule_id("range", col.name),
        rule_type="range",
        column=col.name,
        params={"min": col.min_value, "max": col.max_value},
        confidence=0.7,
        severity="low",
        reason=(
            f"Column '{col.name}' is numeric, observed range "
            f"[{col.min_value}, {col.max_value}]."
        ),
        source="heuristic",
    )


def _generate_freshness(col: ColumnProfile) -> RuleSuggestion | None:
    if col.inferred_semantic_type != "timestamp":
        return None
    return RuleSuggestion(
        rule_id=_next_rule_id("freshness", col.name),
        rule_type="freshness",
        column=col.name,
        params={"max_age_hours": 24},
        confidence=0.75,
        severity="high",
        reason=(
            f"Column '{col.name}' is a timestamp field, checking data freshness "
            f"(max {24}h lag)."
        ),
        source="heuristic",
    )


_GENERATORS = [
    _generate_not_null,
    _generate_unique,
    _generate_accepted_values,
    _generate_range,
    _generate_freshness,
]


def generate_rules(
    profile: ProfileResult,
    llm_key: Optional[str] = None,
    llm_base_url: Optional[str] = None,
    llm_model: str = "deepseek-chat",
) -> list[RuleSuggestion]:
    global _RULE_ID_COUNTER
    _RULE_ID_COUNTER = 0

    rules: list[RuleSuggestion] = []
    for col in profile.columns:
        for gen in _GENERATORS:
            rule = gen(col)
            if rule is not None:
                rules.append(rule)

    if llm_key:
        try:
            from dqdoctor.llm.client import suggest_rules_llm
            llm_rules = suggest_rules_llm(
                profile.columns,
                api_key=llm_key,
                base_url=llm_base_url,
                model=llm_model,
            )
            rules.extend(llm_rules)
        except Exception:
            pass

    return rules
