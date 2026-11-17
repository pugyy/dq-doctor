"""SQL rule shape policy (first line of defence, not the only one).

Two layers guard operator-authored SQL:

1. **This policy** - reject obviously non-read-only or filesystem-reaching
   statements before they reach a driver.
2. **Connection restriction** - SQL rules run on a connection opened with
   DuckDB ``enable_external_access=false``, which blocks file reads
   (``query_table``, ``glob``, replacement scans, ``read_*``) and extension
   loading at the engine level. That is the authoritative guard; a keyword
   blacklist alone is not sufficient and is not treated as such.

Ordering here matters: string literals are removed **before** comments, so
``SELECT '--' ; DELETE FROM t`` cannot hide the ``DELETE`` behind a fake
comment marker.
"""
from __future__ import annotations

import re
from typing import Any

# Keywords that may not appear in a rule statement. PostgreSQL allows
# data-modifying CTEs (`WITH d AS (DELETE ... RETURNING *) SELECT ...`), so a
# leading WITH is not by itself proof of read-only.
#
# `replace` is deliberately NOT here: REPLACE() is a standard string function,
# and `SELECT replace(name,'a','b') FROM t` is a legitimate cleaning rule. The
# MySQL `REPLACE INTO` statement form is caught by the leading-keyword check.
_WRITE_KEYWORDS = (
    "insert", "update", "delete", "merge", "upsert", "truncate", "create",
    "drop", "alter", "grant", "revoke", "copy", "attach", "detach", "install",
    "load", "export", "call", "vacuum", "reindex",
)

# Functions that read local files or reach the network. Covered
# authoritatively by enable_external_access=false on DuckDB; still rejected
# here so the failure is a clear policy message, and so SQL backends get the
# same treatment.
_IO_FUNCTIONS = (
    "read_text", "read_text_auto", "read_blob", "read_csv", "read_csv_auto",
    "read_parquet", "read_json", "read_json_auto", "read_json_objects",
    "read_ndjson", "read_ndjson_auto", "read_xlsx", "parquet_scan",
    "csv_scan", "json_scan", "sniff_csv", "parquet_metadata",
    "parquet_schema", "parquet_file_metadata", "parquet_kv_metadata",
    "delta_scan", "iceberg_scan", "query_table", "query", "glob",
    "pg_read_file", "pg_read_binary_file", "pg_ls_dir", "pg_stat_file",
    "lo_import", "lo_export", "load_file", "pg_file_write", "pg_file_rename",
    "pg_file_unlink", "pg_file_sync", "pg_ls_waldir", "pg_ls_logdir",
    "pg_ls_tmpdir",
)

# DuckDB replacement scans: a single-quoted literal used as a *table* source
# is read from disk. It appears after FROM, after JOIN, or after a comma in a
# table list, so all three forms are matched. (Quoted identifiers are not
# paths and are left alone.)
_REPLACEMENT_SCAN = re.compile(
    r"(?:\bfrom|\bjoin|,)\s*'(?:''|[^'])*'", re.IGNORECASE
)

# A leading parenthesis is legal: `(SELECT 1) UNION (SELECT 2)`.
_SINGLE_QUOTED = re.compile(r"'(?:''|[^'])*'", re.DOTALL)
_DOUBLE_QUOTED = re.compile(r'"(?:""|[^"])*"', re.DOTALL)
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_LINE_COMMENT = re.compile(r"--[^\n]*")
_WORD = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\b")
_TRIPLE_QUOTED = re.compile(r"\$\$.*?\$\$", re.DOTALL)


def _strip_literals(sql: str) -> str:
    """Remove string/dollar-quoted literals, keeping identifier quotes.

    Must run before comment stripping: otherwise a ``--`` inside a literal
    would comment out the rest of the statement and hide a second command.
    """
    out = _TRIPLE_QUOTED.sub("''", sql)
    return _SINGLE_QUOTED.sub("''", out)


def _strip_quoted_identifiers(sql: str) -> str:
    """Remove ``"quoted identifiers"`` so their contents are not keywords.

    ``SELECT "copy" FROM t`` selects a column named copy; without this it
    looks exactly like the COPY statement.
    """
    return _DOUBLE_QUOTED.sub('""', sql)


def _strip_comments(sql: str) -> str:
    without_blocks = _BLOCK_COMMENT.sub(" ", sql)
    return _LINE_COMMENT.sub(" ", without_blocks)


def _normalized(sql: str) -> str:
    """Literal/identifier-free, comment-free text for keyword scanning."""
    return _strip_comments(_strip_quoted_identifiers(_strip_literals(sql)))


def read_only_problem(operator_query: str) -> str | None:
    """Return a problem description, or None for an acceptable query."""
    if not operator_query.strip():
        return "empty query"

    literal_free = _strip_literals(operator_query)
    # Multi-statement check runs on literal-stripped text so semicolons
    # inside string literals are not mistaken for statement separators.
    if ";" in _strip_comments(literal_free).rstrip().rstrip(";"):
        return "multiple statements are not allowed in SQL rules"

    cleaned = _normalized(operator_query).strip().lstrip("(").lstrip()
    if not cleaned:
        return "no statement found (only comments?)"
    head = cleaned.split(None, 1)[0].upper()
    if head not in ("SELECT", "VALUES", "WITH"):
        return "only SELECT/WITH queries are allowed in SQL rules"

    lowered = cleaned.lower()
    # MySQL's REPLACE INTO is a write statement; REPLACE() is a string
    # function and must stay allowed, so it is checked as a statement form.
    if re.search(r"^\s*replace\s+into\b", lowered):
        return "'REPLACE INTO' is not allowed in SQL rules (read-only only)"
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
                "readers bypass the read-only guarantee"
            )

    if _REPLACEMENT_SCAN.search(literal_free):
        return (
            "reading a file directly in FROM is not allowed in SQL rules "
            "(replacement scan); query a table instead"
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
    """Lower-cased word tokens (literals/comments stripped) - for tests."""
    return {m.group(1).lower() for m in _WORD.finditer(_normalized(operator_query))}
