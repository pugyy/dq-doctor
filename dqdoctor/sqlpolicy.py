"""SQL rule contract validation (pure, no database access).

Runs before any execution so malformed rule definitions produce a declared
SKIP/ERROR instead of a driver-side surprise. Kept separate from execution
so the policy side is trivially auditable.
"""
from __future__ import annotations

from typing import Any, Optional


def read_only_problem(operator_query: str) -> Optional[str]:
    """Return a problem description, or None for an acceptable query."""
    if not operator_query.strip():
        return "empty query"
    head = operator_query.split(None, 1)[0].lstrip("(").upper()
    if head not in ("SELECT", "WITH"):
        return "only SELECT/WITH queries are allowed in SQL rules"
    if ";" in operator_query.rstrip().rstrip(";"):
        return "multiple statements are not allowed in SQL rules"
    return None


def expect_problem(expect: Any) -> Optional[str]:
    if not isinstance(expect, dict):
        return "expect must be a mapping like {mode: lte, max: 5}"
    if expect.get("mode", "eq") not in ("eq", "lte", "gte", "between"):
        return f"unsupported expect mode {expect.get('mode')!r}"
    if not ({"value", "min", "max"} & set(expect)):
        return "expect needs one of: value, min, max"
    return None
