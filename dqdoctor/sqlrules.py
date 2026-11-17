"""User-defined SQL rules (guarded, opt-in).

A SQL rule is a query the operator wrote in their own contract file to
check their own data. 1.0 wraps it in guardrails instead of trying to
parameterize the whole statement:

1. ``dqdoctor.sqlpolicy`` validates shape: single statement, SELECT/WITH.
2. Sessions are read-only (see ``datasources``/``engine``).
3. Timeouts: statement timeout (SQL backends) / watchdog+interrupt (DuckDB).
4. Scalar contract: exactly one row, one column.

The execution primitive lives in ``dqdoctor.sqlexec``. If that module is
unavailable, sql rules degrade to an explicit ERROR result - never a
silent pass.
"""
from __future__ import annotations

from dqdoctor.models import RuleResult, RuleSpec, RuleStatus
from dqdoctor.sqlpolicy import expect_problem, read_only_problem


def check_sql(con, spec: RuleSpec, timeout: float) -> RuleResult:
    operator_query = str(spec.params.get("query") or "").strip()
    expect = spec.params.get("expect") or {"mode": "eq", "value": 0}

    problem = read_only_problem(operator_query)
    if problem is not None:
        return _error(spec, problem)
    problem = expect_problem(expect)
    if problem is not None:
        return _skip(spec, problem)

    try:
        from dqdoctor.sqlexec import run_operator_query
    except ImportError:  # pragma: no cover - optional primitive
        return _error(
            spec,
            "sql rule execution primitive is not available in this install; "
            "use regex/row_count/cross_field rules instead",
        )

    try:
        actual = run_operator_query(con, operator_query, timeout)
    except TimeoutError as exc:
        return _error(spec, str(exc))
    except Exception as exc:  # noqa: BLE001 - surfaced as ERROR results
        return _error(spec, f"query failed: {type(exc).__name__}: {exc}")

    from dqdoctor import rules as R

    try:
        ok, message = R.evaluate_scalar(actual, expect)
    except ValueError as exc:
        return _skip(spec, str(exc))
    return RuleResult(
        rule_id=spec.id,
        rule_type="sql",
        column="*",
        status=RuleStatus.PASS if ok else RuleStatus.FAIL,
        severity=spec.severity,
        failed_count=0 if ok else 1,
        total_count=1,
        message=f"SQL rule: {message}",
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
