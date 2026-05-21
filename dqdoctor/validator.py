from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from dqdoctor.connectors.duckdb import get_connection
from dqdoctor.models import RuleSuggestion, ValidationResult


def _quote(name: str) -> str:
    return f'"{name}"'


def _validate_not_null(con, table: str, rule: RuleSuggestion) -> ValidationResult:
    col = _quote(rule.column)
    total = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    failed = con.execute(
        f"SELECT COUNT(*) FROM {table} WHERE {col} IS NULL"
    ).fetchone()[0]
    return ValidationResult(
        rule_id=rule.rule_id,
        rule_type="not_null",
        column=rule.column,
        passed=failed == 0,
        failed_count=failed,
        total_count=total,
        message=(
            f"All {total} rows have non-null '{rule.column}'."
            if failed == 0
            else f"Found {failed}/{total} nulls in '{rule.column}'."
        ),
    )


def _validate_unique(con, table: str, rule: RuleSuggestion) -> ValidationResult:
    col = _quote(rule.column)
    total = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    distinct = con.execute(
        f"SELECT COUNT(DISTINCT {col}) FROM {table}"
    ).fetchone()[0]
    failed = total - distinct
    return ValidationResult(
        rule_id=rule.rule_id,
        rule_type="unique",
        column=rule.column,
        passed=failed == 0,
        failed_count=failed,
        total_count=total,
        message=(
            f"All {total} values in '{rule.column}' are unique."
            if failed == 0
            else f"Found {failed} duplicate values in '{rule.column}'."
        ),
    )


def _validate_accepted_values(
    con, table: str, rule: RuleSuggestion,
) -> ValidationResult:
    col = _quote(rule.column)
    allowed: list[Any] = rule.params.get("values", [])
    if not allowed:
        return ValidationResult(
            rule_id=rule.rule_id,
            rule_type="accepted_values",
            column=rule.column,
            passed=True,
            failed_count=0,
            total_count=0,
            message="No accepted values defined, skipping.",
        )
    placeholders = ", ".join(["?"] * len(allowed))
    total = con.execute(
        f"SELECT COUNT(*) FROM {table} WHERE {col} IS NOT NULL"
    ).fetchone()[0]
    failed = con.execute(
        f"SELECT COUNT(*) FROM {table} "
        f"WHERE {col} NOT IN ({placeholders}) AND {col} IS NOT NULL",
        allowed,
    ).fetchone()[0]
    return ValidationResult(
        rule_id=rule.rule_id,
        rule_type="accepted_values",
        column=rule.column,
        passed=failed == 0,
        failed_count=failed,
        total_count=total,
        message=(
            f"All {total} non-null values in '{rule.column}' "
            f"are in accepted set."
            if failed == 0
            else (
                f"Found {failed}/{total} values outside accepted set "
                f"in '{rule.column}'."
            )
        ),
    )


def _validate_range(con, table: str, rule: RuleSuggestion) -> ValidationResult:
    col = _quote(rule.column)
    min_val = rule.params.get("min")
    max_val = rule.params.get("max")
    if min_val is None or max_val is None:
        return ValidationResult(
            rule_id=rule.rule_id,
            rule_type="range",
            column=rule.column,
            passed=True,
            failed_count=0,
            total_count=0,
            message="No range defined, skipping.",
        )
    total = con.execute(
        f"SELECT COUNT(*) FROM {table} WHERE {col} IS NOT NULL"
    ).fetchone()[0]
    failed = con.execute(
        f"SELECT COUNT(*) FROM {table} WHERE {col} < ? OR {col} > ?",
        [min_val, max_val],
    ).fetchone()[0]
    return ValidationResult(
        rule_id=rule.rule_id,
        rule_type="range",
        column=rule.column,
        passed=failed == 0,
        failed_count=failed,
        total_count=total,
        message=(
            f"All {total} values in '{rule.column}' "
            f"are within [{min_val}, {max_val}]."
            if failed == 0
            else (
                f"Found {failed}/{total} values outside "
                f"[{min_val}, {max_val}] in '{rule.column}'."
            )
        ),
    )


def _validate_freshness(
    con, table: str, rule: RuleSuggestion,
) -> ValidationResult:
    col = _quote(rule.column)
    max_age_hours = rule.params.get("max_age_hours", 24)

    max_ts_row = con.execute(
        f"SELECT MAX({col}) FROM {table} WHERE {col} IS NOT NULL"
    ).fetchone()

    if max_ts_row is None or max_ts_row[0] is None:
        return ValidationResult(
            rule_id=rule.rule_id,
            rule_type="freshness",
            column=rule.column,
            passed=False,
            failed_count=1,
            total_count=1,
            message=f"No data found in '{rule.column}'.",
        )

    max_ts = max_ts_row[0]
    if isinstance(max_ts, str):
        max_ts = datetime.fromisoformat(max_ts)

    now = datetime.now(tz=max_ts.tzinfo) if max_ts.tzinfo else datetime.now()
    age = now - max_ts
    age_hours = age.total_seconds() / 3600
    passed = age_hours <= max_age_hours

    return ValidationResult(
        rule_id=rule.rule_id,
        rule_type="freshness",
        column=rule.column,
        passed=passed,
        failed_count=0 if passed else 1,
        total_count=1,
        message=(
            f"Latest value in '{rule.column}' is {age_hours:.1f}h old "
            f"(max {max_age_hours}h)."
            if passed
            else (
                f"Data in '{rule.column}' is {age_hours:.1f}h old, "
                f"exceeds {max_age_hours}h threshold."
            )
        ),
    )


_VALIDATORS = {
    "not_null": _validate_not_null,
    "unique": _validate_unique,
    "accepted_values": _validate_accepted_values,
    "range": _validate_range,
    "freshness": _validate_freshness,
}


def validate_rules(
    db_path: "str | Path",
    table_name: str,
    rules: list[RuleSuggestion],
) -> list[ValidationResult]:
    con = get_connection(db_path)
    try:
        results: list[ValidationResult] = []
        quoted_table = _quote(table_name)
        for rule in rules:
            validator = _VALIDATORS.get(rule.rule_type)
            if validator is None:
                results.append(ValidationResult(
                    rule_id=rule.rule_id,
                    rule_type=rule.rule_type,
                    column=rule.column,
                    passed=True,
                    failed_count=0,
                    total_count=0,
                    message=f"Unknown rule type '{rule.rule_type}', skipped.",
                ))
                continue
            results.append(validator(con, quoted_table, rule))
        return results
    finally:
        con.close()
