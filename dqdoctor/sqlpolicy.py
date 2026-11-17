"""SQL rule shape policy (pure, no database access).

Runs before execution so malformed or dangerous rule statements produce a
declared SKIP/ERROR instead of a driver-side surprise.

This is a *shape* guard, not a full SQL parser: it rejects the cases that
make "read-only single statement" untrue in practice. Sessions are also
opened read-only (PostgreSQL/MySQL) or read-only (DuckDB file), and DuckDB
file/HTTP reader functions are blocked because a read-only session does not
prevent them from touching the filesystem.

Known limits (documented): a determined author can still write an expensive
read-only query; the statement timeout is the mitigation.
"""
from __future__ import annotations

import re
from typing import Any

# Keywords that may not appear in a rule statement. PostgreSQL allows
# data-modifying CTEs (`WITH d AS (DELETE ... RETURNING *) SELECT ...`), so a
# leading WITH is not by itself proof of read-only.
_WRITE_KEYWORDS = (
    "insert", "update", "delete", "merge", "upsert", "truncate", "create",
    "drop", "alter", "grant", "revoke", "copy", "attach", "detach", "install",
    "load", "export", "call", "vacuum", "reindex",
)

# Functions that read local files or reach the network. A read-only session
# does not stop DuckDB from doing either.
_IO_FUNCTIONS = (
    "read_text", "read_blob", "read_csv", "read_csv_auto", "read_parquet",
    "read_json", "read_json_auto", "read_ndjson", "parquet_scan", "csv_scan",
    "json_scan", "read_xlsx", "sniff_csv", "delta_scan", "iceberg_scan",
)

_LINE_COMMENT = re.compile(r"--[^\n]*")
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_SINGLE_QUOTED = re.compile(r"'(?:''|[^'])*'")
_DOUBLE_QUOTED = re.compile(r'"(?:""|[^"])*"')
_WORD = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\b")


def _strip_noise(sql: str) -> str:
    """Remove comments and string/identifier literals for keyword scanning."""
    without_blocks = _BLOCK_COMMENT.sub(" ", sql)
    without_lines = _LINE_COMMENT.sub(" ", without_blocks)
    without_strings = _SINGLE_QUOTED.sub("''", without_lines)
    return _DOUBLE_QUOTED.sub('""', without_strings)


def read_only_problem(operator_query: str) -> str | None:
    """Return a problem description, or None for an acceptable query."""
    if not operator_query.strip():
        return "empty query"
    cleaned = _strip_noise(operator_query).strip()
    head = cleaned.split(None, 1)[0].upper() if cleaned else ""
    if head not in ("SELECT", "WITH"):
        return "only SELECT/WITH queries are allowed in SQL rules"

    # Multi-statement: a semicolon anywhere but the very end of the statement.
    if ";" in cleaned.rstrip().rstrip(";"):
        return "multiple statements are not allowed in SQL rules"

    lowered = cleaned.lower()
    for word in _WRITE_KEYWORDS:
        if re.search(r"\b" + word + r"\b", lowered):
            return (
                f"'{word.upper()}' is not allowed in SQL rules "
                "(read-only only; this includes data-modifying CTEs)"
            )

    for fn in _IO_FUNCTIONS:
        if re.search(r"\b" + fn + r"\s*\(", lowered):
            return (
                f"'{fn}' is not allowed in SQL rules: file and network "
                "readers bypass read-only sessions"
            )
    return None


def expect_problem(expect: Any) -> str | None:
    if not isinstance(expect, dict):
        return "expect must be a mapping like {mode: lte, max: 5}"
    if expect.get("mode", "eq") not in ("eq", "lte", "gte", "between"):
        return f"unsupported expect mode {expect.get('mode')!r}"
    if not ({"value", "min", "max"} & set(expect)):
        return "expect needs one of: value, min, max"
    return None


def statement_words(operator_query: str) -> set[str]:
    """Lower-cased word tokens (comments/literals stripped) - for tests."""
    return {m.group(1).lower() for m in _WORD.finditer(_strip_noise(operator_query))}
