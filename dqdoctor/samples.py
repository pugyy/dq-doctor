"""Sample-value fetches for profiling and PII evidence.

Each branch assembles its own statement literal from a quoted identifier
and a scan fragment; limits are bound parameters.
"""
from __future__ import annotations

from dqdoctor.scanref import ScanRef


def sample_values(con, scan: ScanRef, qc: str, limit: int = 10) -> list:
    con.query_count += 1
    if con.backend == "duckdb":
        if scan.params is None:
            rows = con._raw.execute(
                "SELECT DISTINCT " + qc + " FROM " + scan.fragment
                + " WHERE " + qc + " IS NOT NULL LIMIT 10"
            ).fetchall()
        else:
            # the scan fragment's own bound LIMIT binds first
            rows = con._raw.execute(
                "SELECT DISTINCT " + qc + " FROM " + scan.fragment
                + " WHERE " + qc + " IS NOT NULL LIMIT ?",
                (scan.params[0], int(limit)),
            ).fetchall()
        return [r[0] for r in rows]
    from sqlalchemy import text

    if scan.params is None:
        rows = con._raw.execute(
            text(
                "SELECT DISTINCT " + qc + " FROM " + scan.fragment
                + " WHERE " + qc + " IS NOT NULL LIMIT 10"
            )
        ).fetchall()
    else:
        rows = con._raw.execute(
            text(
                "SELECT DISTINCT " + qc + " FROM " + scan.fragment
                + " WHERE " + qc + " IS NOT NULL LIMIT :k"
            ),
            {"n": scan.params[0], "k": int(limit)},
        ).fetchall()
    return [r[0] for r in rows]
