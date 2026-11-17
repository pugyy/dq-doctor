"""Rule types, validation and pure evaluation logic.

The SQL execution lives in ``dqdoctor.rulecheck``; this module owns the
rule contract semantics: which rule types exist, what parameters they
take, and the non-SQL parts of evaluation (freshness clock math, row
count comparisons, timestamp parsing).

Decimal/float boundaries keep their numeric identity end to end: contract
loaders parse numeric strings to ``Decimal`` when precision matters, and
values are bound as parameters so the engine never reformats them.
"""
from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

RULE_TYPES = (
    "not_null",
    "unique",
    "accepted_values",
    "range",
    "freshness",
    "regex",
    "row_count",
    "cross_field",
    "sql",
)

CROSS_FIELD_OPS = ("<", "<=", ">", ">=", "=", "!=", "<>")


def default_rule_id(rule_type: str, column: str) -> str:
    return f"{rule_type}:{column}"


def validate_spec(spec: dict, index: int) -> dict:
    """Validate one raw rule mapping; raise ValueError with a clear message."""
    rule_id = str(spec.get("id") or "")
    rule_type = str(spec.get("type") or "")
    column = str(spec.get("column") or "*")
    if not rule_id:
        if rule_type and column != "*":
            rule_id = default_rule_id(rule_type, column)
        else:
            raise ValueError(f"Rule #{index}: 'id' is required")
    if rule_type not in RULE_TYPES:
        raise ValueError(
            f"Rule '{rule_id}': unknown type {rule_type!r}. "
            f"Supported: {', '.join(RULE_TYPES)}"
        )
    if rule_type != "sql" and rule_type != "row_count" and column == "*":
        raise ValueError(f"Rule '{rule_id}': 'column' is required for {rule_type}")
    severity = str(spec.get("severity") or "medium")
    if severity not in ("high", "medium", "low"):
        raise ValueError(f"Rule '{rule_id}': severity must be high/medium/low")
    params = dict(spec.get("params") or {})
    return {
        "id": rule_id,
        "type": rule_type,
        "column": column,
        "params": params,
        "severity": severity,
        "reason": str(spec.get("reason") or ""),
        "source": str(spec.get("source") or "contract"),
        "enabled": bool(spec.get("enabled", True)),
    }


# ---------------------------------------------------------------------------
# Numeric parameter handling (Decimal-safe)


def as_number(value: Any) -> Decimal | int | float:
    """Best numeric form of a rule boundary.

    Strings with a decimal point become ``Decimal`` (precision preserved);
    ints stay ints; floats stay floats. Anything invalid raises ValueError.
    """
    if isinstance(value, bool):
        raise ValueError(f"Expected a number, got bool {value!r}")
    if isinstance(value, int | float | Decimal):
        return value
    text = str(value).strip()
    try:
        if "." in text or "e" in text.lower():
            return Decimal(text)
        return int(text)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"Expected a number, got {value!r}") from exc


# ---------------------------------------------------------------------------
# Freshness evaluation (pure; clock injected for testability)


def parse_timestamp(value: Any) -> datetime:
    """Parse a driver-returned timestamp value into a datetime.

    Strings are parsed as ISO-8601; invalid strings raise ValueError so the
    caller can surface a concrete ERROR result (1.0 requirement: a
    configured string timestamp with invalid values is an error, not a
    silent pass).
    """
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day)
    if isinstance(value, str):
        text = value.strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError as exc:
            raise ValueError(f"Invalid timestamp value {value!r}") from exc
        return parsed
    raise ValueError(f"Cannot interpret timestamp from {value!r}")


def evaluate_freshness(
    max_value: Any,
    max_age_hours: float,
    clock: Callable[[], datetime],
) -> tuple[bool, str]:
    """Evaluate freshness against an injected clock.

    Timezone policy (documented): naive timestamps are treated as local
    wall-clock time - the convention of most ETL-written TIMESTAMP columns.
    Future timestamps fail with an explicit message; data from the future
    is a quality problem, not a bonus.
    """
    ts = parse_timestamp(max_value)
    now = clock()
    local_tz = datetime.now().astimezone().tzinfo or UTC
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=local_tz)
    if now.tzinfo is None:
        now = now.replace(tzinfo=local_tz)
    age_hours = (now - ts).total_seconds() / 3600.0
    if age_hours < -1e-9:
        return False, (
            f"Newest value is {-age_hours:.1f}h in the future "
            f"(max age {max_age_hours}h)."
        )
    if age_hours <= max_age_hours:
        return True, f"Newest value is {age_hours:.1f}h old (max {max_age_hours}h)."
    return False, (
        f"Data is {age_hours:.1f}h old, exceeds {max_age_hours}h threshold."
    )


# ---------------------------------------------------------------------------
# Row-count comparison (pure)


def evaluate_row_count(
    actual: int,
    params: dict[str, Any],
) -> tuple[bool, str]:
    exact = params.get("exact")
    minimum = params.get("min")
    maximum = params.get("max")
    checks = []
    if exact is not None:
        checks.append(("eq", as_number(exact)))
    if minimum is not None:
        checks.append(("ge", as_number(minimum)))
    if maximum is not None:
        checks.append(("le", as_number(maximum)))
    if not checks:
        return False, "row_count rule needs one of exact/min/max"
    for op, bound in checks:
        if op == "eq" and actual != bound:
            return False, f"Row count {actual} != expected {bound}"
        if op == "ge" and actual < bound:
            return False, f"Row count {actual} < minimum {bound}"
        if op == "le" and actual > bound:
            return False, f"Row count {actual} > maximum {bound}"
    return True, f"Row count {actual} within contract bounds"


# ---------------------------------------------------------------------------
# SQL rule scalar contract


def evaluate_scalar(actual: Any, expect: dict[str, Any]) -> tuple[bool, str]:
    """Evaluate a custom SQL rule's scalar result against its contract."""
    mode = str(expect.get("mode", "eq"))
    try:
        value = as_number(actual)
    except ValueError:
        value = actual
    if "value" not in expect and "min" not in expect and "max" not in expect:
        raise ValueError(
            "SQL rule 'expect' needs one of: value, min, max "
            "(e.g. {mode: lte, max: 5})"
        )
    if mode == "eq":
        bound = as_number(expect.get("value", expect.get("max")))
        ok = value == bound
        return ok, f"got {actual}, expected == {bound}"
    if mode == "lte":
        bound = as_number(expect.get("value", expect.get("max")))
        ok = value <= bound
        return ok, f"got {actual}, expected <= {bound}"
    if mode == "gte":
        bound = as_number(expect.get("value", expect.get("min")))
        ok = value >= bound
        return ok, f"got {actual}, expected >= {bound}"
    if mode == "between":
        lo = as_number(expect.get("min"))
        hi = as_number(expect.get("max"))
        ok = lo <= value <= hi
        return ok, f"got {actual}, expected between {lo} and {hi}"
    raise ValueError(f"SQL rule expect mode {mode!r} not supported (eq/lte/gte/between)")


def max_age_from(params: dict[str, Any]) -> float:
    value = params.get("max_age_hours", 24)
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"freshness max_age_hours must be a number, got {value!r}"
        ) from exc


def future_ts(now: datetime, hours: float) -> datetime:  # test helper
    return now + timedelta(hours=hours)
