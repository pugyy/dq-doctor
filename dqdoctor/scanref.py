"""Sampled scan references.

DuckDB DDL/query SAMPLE clauses cannot take bound parameters on any of the
supported engines, so 1.0 samples with a deterministic first-N slice:
``(SELECT * FROM t LIMIT ?)`` with the limit bound as a parameter. That is
portable (DuckDB/PostgreSQL/MySQL), reproducible, and keeps values out of
SQL text. The fragment embeds only a quoted, allowlist-validated table
reference and a fixed LIMIT literal.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ScanRef:
    """A FROM-clause fragment plus its bind parameters."""

    fragment: str
    params: list | None


def full_scan(qt: str) -> ScanRef:
    return ScanRef(fragment=qt, params=None)


def sampled_scan(con, qt: str, limit: int) -> ScanRef:
    if con.backend == "duckdb":
        fragment = "(SELECT * FROM " + qt + " LIMIT ?)"
    else:
        fragment = "(SELECT * FROM " + qt + " LIMIT :n)"
    return ScanRef(fragment=fragment, params=[int(limit)])


def bind_one(con, scan: ScanRef):
    """Parameter container for a scan fragment on this backend."""
    if scan.params is None:
        return None
    if con.backend == "duckdb":
        return scan.params
    return {"n": scan.params[0]}
