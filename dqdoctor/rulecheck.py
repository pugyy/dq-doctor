"""Rule execution for dq-doctor 1.0 (built-in rule types).

Design (batched pushdown): the engine profiles each table first; this
executor reuses those aggregates so the common rules cost **zero** extra
round trips:

- not_null / unique / freshness / row_count read straight off the profile;
- range short-circuits to PASS when the profiled min/max sit inside the
  contract bounds, and only counts violations otherwise;
- accepted_values short-circuits via the profiled distinct-value set for
  low-cardinality columns, and only runs a bound ``NOT IN`` count otherwise;
- regex / cross_field run one aggregate each with bound parameters.

User SQL rules live in ``dqdoctor.sqlrules`` (guarded product feature).
Statements here are literals plus allowlist-quoted identifiers; every
value is bound as a parameter.
"""
from __future__ import annotations

from datetime import datetime
from typing import Callable

from dqdoctor.models import RuleResult, RuleSpec, RuleStatus, TableProfile
from dqdoctor import rules as R


def execute_rules(
    con,
    table: str,
    profile: TableProfile,
    specs: list[RuleSpec],
    clock: Callable[[], datetime],
    sql_timeout: float = 30.0,
) -> list[RuleResult]:
    """Execute built-in contract rules against one table."""
    qt = con.table_ref(table)
    results: list[RuleResult] = []
    for spec in specs:
        if not spec.enabled:
            results.append(_skip(spec, "disabled in contract"))
            continue
        checker = _DISPATCH.get(spec.type)
        if checker is None:
            results.append(_skip(spec, f"unknown rule type {spec.type}"))
            continue
        try:
            results.append(checker(con, qt, profile, spec, clock, sql_timeout))
        except _UnknownColumn as exc:
            results.append(_error(spec, str(exc)))
        except ValueError as exc:
            results.append(_skip(spec, str(exc)))
        except Exception as exc:  # noqa: BLE001 - execution errors stay visible
            results.append(_error(spec, f"{type(exc).__name__}: {exc}"))
    return results


class _UnknownColumn(ValueError):
    pass


def _require_col(profile: TableProfile, name: str):
    col = profile.column(name)
    if col is None:
        raise _UnknownColumn(f"unknown column '{name}' on {profile.table_name}")
    return col


# ---------------------------------------------------------------------------


def check_not_null(con, qt, profile, spec, clock, timeout) -> RuleResult:
    col = _require_col(profile, spec.column)
    failed = col.null_count
    total = profile.row_count
    return RuleResult(
        rule_id=spec.id, rule_type="not_null", column=spec.column,
        status=RuleStatus.PASS if failed == 0 else RuleStatus.FAIL,
        severity=spec.severity, failed_count=failed, total_count=total,
        message=(
            f"All {total} rows have non-null '{spec.column}'."
            if failed == 0
            else f"Found {failed}/{total} nulls in '{spec.column}'."
        ),
        source=spec.source,
    )


def check_unique(con, qt, profile, spec, clock, timeout) -> RuleResult:
    col = _require_col(profile, spec.column)
    # 1.0: uniqueness is judged over NON-NULL values only. NULL presence is
    # the not_null rule's business (0.7 counted NULLs as duplicates).
    nonnull = profile.row_count - col.null_count
    failed = max(nonnull - col.distinct_count, 0) if nonnull else 0
    return RuleResult(
        rule_id=spec.id, rule_type="unique", column=spec.column,
        status=RuleStatus.PASS if failed == 0 else RuleStatus.FAIL,
        severity=spec.severity, failed_count=failed, total_count=nonnull,
        message=(
            f"All {nonnull} non-null values in '{spec.column}' are unique."
            if failed == 0
            else f"Found {failed} duplicate values in '{spec.column}' "
            f"(non-null values only; NULLs are not_null's business)."
        ),
        source=spec.source,
    )


def check_accepted_values(con, qt, profile, spec, clock, timeout) -> RuleResult:
    col = _require_col(profile, spec.column)
    allowed_raw = spec.params.get("values") or []
    if not allowed_raw:
        return _skip(spec, "no accepted values defined")
    allowed = [str(v) for v in allowed_raw]
    null_policy = str(spec.params.get("null_policy", "ignore"))
    nonnull = profile.row_count - col.null_count

    if col.distinct_count <= 20 and col.distinct_values and null_policy == "ignore":
        seen = {str(v) for v in col.distinct_values}
        if not (seen - set(allowed)):
            return RuleResult(
                rule_id=spec.id, rule_type="accepted_values", column=spec.column,
                status=RuleStatus.PASS, severity=spec.severity, failed_count=0,
                total_count=nonnull,
                message=f"All {nonnull} non-null values in '{spec.column}' "
                f"are in the accepted set.",
                source=spec.source,
            )
    return _accepted_values_query(con, qt, profile, spec, allowed, null_policy)


def _accepted_values_query(con, qt, profile, spec, allowed: list[str], null_policy: str):
    """Count values outside the accepted set (bound NOT IN; NULLs per policy)."""
    qc = con.quote_identifier(spec.column)
    con.query_count += 1
    if con.backend == "duckdb":
        placeholders = ", ".join(["?"] * len(allowed))
        row = con._raw.execute(
            "SELECT COUNT(*) FROM " + qt + " WHERE " + qc + " IS NOT NULL AND "
            + qc + " NOT IN (" + placeholders + ")",
            list(allowed),
        ).fetchone()
    else:
        from sqlalchemy import text

        placeholders = ", ".join([":v" + str(i) for i in range(len(allowed))])
        named = {f"v{i}": v for i, v in enumerate(allowed)}
        row = con._raw.execute(
            text(
                "SELECT COUNT(*) FROM " + qt + " WHERE " + qc + " IS NOT NULL AND "
                + qc + " NOT IN (" + placeholders + ")"
            ),
            named,
        ).fetchone()
    col = profile.column(spec.column)
    nonnull = profile.row_count - col.null_count
    failed = row[0]
    if null_policy == "fail":
        failed += col.null_count
        total = profile.row_count
        message_ok = f"All {total} values in '{spec.column}' are in the accepted set."
        message_bad = (
            f"Found {failed}/{total} values outside the accepted set or NULL in "
            f"'{spec.column}' (null_policy=fail)."
        )
    else:
        total = nonnull
        message_ok = (
            f"All {nonnull} non-null values in '{spec.column}' are in the "
            f"accepted set."
        )
        message_bad = (
            f"Found {failed}/{nonnull} values outside the accepted set in "
            f"'{spec.column}' (NULLs ignored per null_policy)."
        )
    return RuleResult(
        rule_id=spec.id, rule_type="accepted_values", column=spec.column,
        status=RuleStatus.PASS if failed == 0 else RuleStatus.FAIL,
        severity=spec.severity, failed_count=failed, total_count=total,
        message=message_ok if failed == 0 else message_bad, source=spec.source,
    )


def check_range(con, qt, profile, spec, clock, timeout) -> RuleResult:
    col = _require_col(profile, spec.column)
    if spec.params.get("min") is None and spec.params.get("max") is None:
        return _skip(spec, "range rule needs min and/or max")
    lo = R.as_number(spec.params["min"]) if spec.params.get("min") is not None else None
    hi = R.as_number(spec.params["max"]) if spec.params.get("max") is not None else None
    nonnull = profile.row_count - col.null_count
    if nonnull == 0:
        return RuleResult(
            rule_id=spec.id, rule_type="range", column=spec.column,
            status=RuleStatus.PASS, severity=spec.severity, failed_count=0,
            total_count=0,
            message=f"No non-null values in '{spec.column}' to check.",
            source=spec.source,
        )
    try:
        in_bounds = (
            lo is not None and col.min_value is not None and col.min_value >= lo
            and hi is not None and col.max_value is not None and col.max_value <= hi
        )
        in_bounds = in_bounds or (
            lo is None and hi is not None and col.max_value is not None
            and col.max_value <= hi
        )
        in_bounds = in_bounds or (
            hi is None and lo is not None and col.min_value is not None
            and col.min_value >= lo
        )
    except TypeError:
        in_bounds = False
    if in_bounds:
        return RuleResult(
            rule_id=spec.id, rule_type="range", column=spec.column,
            status=RuleStatus.PASS, severity=spec.severity, failed_count=0,
            total_count=nonnull,
            message=f"All {nonnull} values in '{spec.column}' within "
            f"[{lo}, {hi}] (short-circuited from profiled min/max).",
            source=spec.source,
        )
    return _range_query(con, qt, spec, lo, hi, nonnull)


def _range_query(con, qt, spec, lo, hi, nonnull) -> RuleResult:
    qc = con.quote_identifier(spec.column)
    con.query_count += 1
    if con.backend == "duckdb":
        if lo is not None and hi is not None:
            row = con._raw.execute(
                "SELECT COUNT(*) FROM " + qt + " WHERE " + qc + " < ? OR "
                + qc + " > ?",
                [lo, hi],
            ).fetchone()
        elif lo is not None:
            row = con._raw.execute(
                "SELECT COUNT(*) FROM " + qt + " WHERE " + qc + " < ?",
                [lo],
            ).fetchone()
        else:
            row = con._raw.execute(
                "SELECT COUNT(*) FROM " + qt + " WHERE " + qc + " > ?",
                [hi],
            ).fetchone()
    else:
        from sqlalchemy import text

        if lo is not None and hi is not None:
            row = con._raw.execute(
                text("SELECT COUNT(*) FROM " + qt + " WHERE " + qc
                     + " < :lo OR " + qc + " > :hi"),
                {"lo": lo, "hi": hi},
            ).fetchone()
        elif lo is not None:
            row = con._raw.execute(
                text("SELECT COUNT(*) FROM " + qt + " WHERE " + qc + " < :lo"),
                {"lo": lo},
            ).fetchone()
        else:
            row = con._raw.execute(
                text("SELECT COUNT(*) FROM " + qt + " WHERE " + qc + " > :hi"),
                {"hi": hi},
            ).fetchone()
    failed = row[0]
    bounds = f"[{lo}, {hi}]"
    return RuleResult(
        rule_id=spec.id, rule_type="range", column=spec.column,
        status=RuleStatus.PASS if failed == 0 else RuleStatus.FAIL,
        severity=spec.severity, failed_count=failed, total_count=nonnull,
        message=(
            f"All {nonnull} values in '{spec.column}' within {bounds}."
            if failed == 0
            else f"Found {failed}/{nonnull} values outside {bounds} in "
            f"'{spec.column}'."
        ),
        source=spec.source,
    )


def check_freshness(con, qt, profile, spec, clock, timeout) -> RuleResult:
    col = _require_col(profile, spec.column)
    from dqdoctor.profiling import is_temporal

    if not is_temporal(col.dtype):
        return _skip(
            spec,
            f"column '{spec.column}' has type {col.dtype}; freshness needs "
            "a TIMESTAMP/DATE column",
        )
    max_age = R.max_age_from(spec.params)
    if col.max_value is None:
        return RuleResult(
            rule_id=spec.id, rule_type="freshness", column=spec.column,
            status=RuleStatus.FAIL, severity=spec.severity, failed_count=1,
            total_count=1,
            message=f"No non-null values in '{spec.column}' to evaluate freshness.",
            source=spec.source,
        )
    try:
        ok, message = R.evaluate_freshness(col.max_value, max_age, clock)
    except ValueError as exc:
        return _error(spec, str(exc))
    return RuleResult(
        rule_id=spec.id, rule_type="freshness", column=spec.column,
        status=RuleStatus.PASS if ok else RuleStatus.FAIL,
        severity=spec.severity, failed_count=0 if ok else 1, total_count=1,
        message=message, source=spec.source,
    )


def check_row_count(con, qt, profile, spec, clock, timeout) -> RuleResult:
    ok, message = R.evaluate_row_count(profile.row_count, spec.params)
    return RuleResult(
        rule_id=spec.id, rule_type="row_count", column="*",
        status=RuleStatus.PASS if ok else RuleStatus.FAIL,
        severity=spec.severity, failed_count=0 if ok else 1,
        total_count=profile.row_count, message=message, source=spec.source,
    )


def check_regex(con, qt, profile, spec, clock, timeout) -> RuleResult:
    col = _require_col(profile, spec.column)
    pattern = str(spec.params.get("pattern") or "")
    if not pattern:
        return _skip(spec, "regex rule needs params.pattern")
    qc = con.quote_identifier(spec.column)
    nonnull = profile.row_count - col.null_count
    con.query_count += 1
    if con.backend == "duckdb":
        row = con._raw.execute(
            "SELECT COUNT(*) FROM " + qt + " WHERE " + qc
            + " IS NOT NULL AND NOT regexp_matches(" + qc + ", ?)",
            [pattern],
        ).fetchone()
    elif con.backend == "postgresql":
        from sqlalchemy import text

        row = con._raw.execute(
            text("SELECT COUNT(*) FROM " + qt + " WHERE " + qc
                 + " IS NOT NULL AND " + qc + " !~ :p"),
            {"p": pattern},
        ).fetchone()
    else:
        from sqlalchemy import text

        row = con._raw.execute(
            text("SELECT COUNT(*) FROM " + qt + " WHERE " + qc
                 + " IS NOT NULL AND NOT REGEXP_LIKE(" + qc + ", :p)"),
            {"p": pattern},
        ).fetchone()
    failed = row[0]
    return RuleResult(
        rule_id=spec.id, rule_type="regex", column=spec.column,
        status=RuleStatus.PASS if failed == 0 else RuleStatus.FAIL,
        severity=spec.severity, failed_count=failed, total_count=nonnull,
        message=(
            f"All {nonnull} non-null values in '{spec.column}' match the pattern."
            if failed == 0
            else f"Found {failed}/{nonnull} values in '{spec.column}' not "
            f"matching the pattern."
        ),
        source=spec.source,
    )


def check_cross_field(con, qt, profile, spec, clock, timeout) -> RuleResult:
    left = str(spec.params.get("left") or "")
    right = str(spec.params.get("right") or "")
    op = str(spec.params.get("op") or ">=")
    if not left or not right:
        return _skip(spec, "cross_field rule needs params.left and params.right")
    if op not in R.CROSS_FIELD_OPS:
        return _skip(spec, f"cross_field op must be one of {R.CROSS_FIELD_OPS}")
    _require_col(profile, left)
    _require_col(profile, right)
    ql = con.quote_identifier(left)
    qr_ = con.quote_identifier(right)
    predicate = "(" + ql + " " + op + " " + qr_ + ") IS NOT TRUE"
    con.query_count += 1
    if con.backend == "duckdb":
        row = con._raw.execute(
            "SELECT COUNT(*) FROM " + qt + " WHERE " + predicate
        ).fetchone()
    else:
        from sqlalchemy import text

        row = con._raw.execute(
            text("SELECT COUNT(*) FROM " + qt + " WHERE " + predicate)
        ).fetchone()
    failed = row[0]
    return RuleResult(
        rule_id=spec.id, rule_type="cross_field", column=f"{left},{right}",
        status=RuleStatus.PASS if failed == 0 else RuleStatus.FAIL,
        severity=spec.severity, failed_count=failed,
        total_count=profile.row_count,
        message=(
            f"'{left} {op} {right}' holds on all {profile.row_count} rows."
            if failed == 0
            else f"'{left} {op} {right}' violated on {failed}/{profile.row_count} "
            f"rows (NULL comparisons count as violations)."
        ),
        source=spec.source,
    )


def _skip(spec: RuleSpec, why: str) -> RuleResult:
    return RuleResult(
        rule_id=spec.id, rule_type=spec.type, column=spec.column,
        status=RuleStatus.SKIP, severity=spec.severity, message=why,
        source=spec.source,
    )


def _error(spec: RuleSpec, why: str) -> RuleResult:
    return RuleResult(
        rule_id=spec.id, rule_type=spec.type, column=spec.column,
        status=RuleStatus.ERROR, severity=spec.severity, message=why,
        source=spec.source,
    )


_DISPATCH = {
    "not_null": check_not_null,
    "unique": check_unique,
    "accepted_values": check_accepted_values,
    "range": check_range,
    "freshness": check_freshness,
    "row_count": check_row_count,
    "regex": check_regex,
    "cross_field": check_cross_field,
}
