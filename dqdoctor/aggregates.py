"""Aggregate SQL used by the profiler.

Each function assembles its statement from literals and allowlist-validated
quoted identifiers, then runs it in place. Sample limits arrive bound via
``ScanRef`` (see ``dqdoctor.scanref``). Values never appear in SQL text.
"""
from __future__ import annotations

from dqdoctor.scanref import ScanRef, bind_one


def count_scan(con, scan: ScanRef) -> int:
    """Row count of a scan (full or sampled); limits stay bound."""
    con.query_count += 1
    stmt_duck = "SELECT COUNT(*) FROM "
    stmt_sqla = "SELECT COUNT(*) FROM "
    if con.backend == "duckdb":
        return con._raw.execute(
            stmt_duck + scan.fragment, bind_one(con, scan)
        ).fetchone()[0]
    from sqlalchemy import text

    return con._raw.execute(
        text(stmt_sqla + scan.fragment), bind_one(con, scan)
    ).fetchone()[0]


def aggregate(
    con, scan: ScanRef, quoted_columns: list[tuple[str, str, bool]]
) -> tuple[int, dict]:
    """One aggregate SELECT for the whole table profile.

    ``quoted_columns``: (column name, quoted identifier, want_min_max).
    Returns (row_count, {name: {"nonnull", "distinct", "min", "max"}}).
    """
    selects = ["COUNT(*)"]
    layout: dict[str, dict] = {}
    index = 1
    for name, qc, want_min_max in quoted_columns:
        layout[name] = {"nonnull": index, "distinct": index + 1}
        selects.append("COUNT(" + qc + ")")
        selects.append("COUNT(DISTINCT " + qc + ")")
        index += 2
        if want_min_max:
            selects.append("MIN(" + qc + ")")
            selects.append("MAX(" + qc + ")")
            layout[name]["min"] = index
            layout[name]["max"] = index + 1
            index += 2
    select_list = ", ".join(selects)
    con.query_count += 1
    if con.backend == "duckdb":
        row = con._raw.execute(
            "SELECT " + select_list + " FROM " + scan.fragment,
            bind_one(con, scan),
        ).fetchone()
    else:
        from sqlalchemy import text

        row = con._raw.execute(
            text("SELECT " + select_list + " FROM " + scan.fragment),
            bind_one(con, scan),
        ).fetchone()
    return row[0], {
        name: {
            "nonnull": row[pos["nonnull"]],
            "distinct": row[pos["distinct"]],
            "min": row[pos["min"]] if "min" in pos else None,
            "max": row[pos["max"]] if "max" in pos else None,
        }
        for name, pos in layout.items()
    }


def distinct_values(con, qt: str, qc: str) -> list:
    con.query_count += 1
    if con.backend == "duckdb":
        rows = con._raw.execute(
            "SELECT DISTINCT " + qc + " FROM " + qt
            + " WHERE " + qc + " IS NOT NULL ORDER BY " + qc + " LIMIT 21"
        ).fetchall()
    else:
        from sqlalchemy import text

        rows = con._raw.execute(
            text("SELECT DISTINCT " + qc + " FROM " + qt
                 + " WHERE " + qc + " IS NOT NULL ORDER BY " + qc + " LIMIT 21")
        ).fetchall()
    return [r[0] for r in rows][:20]
