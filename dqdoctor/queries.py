"""Named query helpers for dq-doctor 1.0.

Each function runs one fixed statement with bound parameter values:
named binds through SQLAlchemy ``text()`` on SQL backends, positional
``?`` binds on DuckDB. There is no generic ``execute(sql)`` entry point;
statements are literals at their execution site and values only travel
through the driver's bind path.
"""
from __future__ import annotations


def list_tables(con) -> list[str]:
    """List user tables for the connection's backend and scope.

    ``DATABASE()`` is MySQL-only; PostgreSQL must use the search_path schema
    (default ``public``). Branching on ``backend`` rather than on "schema is
    set" is what keeps the default PostgreSQL URL working.
    """
    if con.backend == "duckdb":
        rows = con._raw.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'main' ORDER BY table_name"
        ).fetchall()
        con.query_count += 1
        return [r[0] for r in rows]
    from sqlalchemy import text

    con.query_count += 1
    if con.backend == "mysql":
        # MySQL has no separate schema: ?schema= selects the database in the
        # URL, so the current database is always the right filter.
        rows = con._raw.execute(
            text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = DATABASE() ORDER BY table_name"
            )
        ).fetchall()
        return [r[0] for r in rows]
    result = con._raw.execute(
        text(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = :schema ORDER BY table_name"
        ),
        {"schema": con.sql_schema},
    )
    return [r[0] for r in result.fetchall()]


def table_columns(con, table: str) -> list[dict]:
    """Column metadata as [{"name": ..., "dtype": ...}, ...].

    ``table`` (and the schema on SQL backends) are bound parameters.
    """
    if con.source_kind == "files":
        result = con._raw.execute(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_name = ? ORDER BY ordinal_position",
            (table,),
        )
        rows = result.fetchall()
    elif con.backend == "duckdb":
        result = con._raw.execute(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_schema = 'main' AND table_name = ? "
            "ORDER BY ordinal_position",
            (table,),
        )
        rows = result.fetchall()
    else:
        from sqlalchemy import text

        if con.backend == "mysql":
            result = con._raw.execute(
                text(
                    "SELECT column_name, data_type FROM information_schema.columns "
                    "WHERE table_schema = DATABASE() AND table_name = :table "
                    "ORDER BY ordinal_position"
                ),
                {"table": table},
            )
        else:
            result = con._raw.execute(
                text(
                    "SELECT column_name, data_type FROM information_schema.columns "
                    "WHERE table_schema = :schema AND table_name = :table "
                    "ORDER BY ordinal_position"
                ),
                {"schema": con.sql_schema, "table": table},
            )
        rows = result.fetchall()
    con.query_count += 1
    return [{"name": r[0], "dtype": r[1]} for r in rows]
