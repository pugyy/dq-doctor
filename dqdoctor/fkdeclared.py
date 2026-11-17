"""Declared foreign-key metadata.

Reads DB-declared FK constraints (DuckDB ``duckdb_constraints``,
PostgreSQL/MySQL ``information_schema``), covering composite keys and
cross-schema directions. Statements are fixed literals with the schema
name bound as a parameter.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class FKRelationship:
    from_table: str
    from_columns: list[str]
    to_table: str
    to_columns: list[str]
    declared: bool = True
    confidence: float = 1.0


@dataclass
class FKPlan:
    relationships: list[FKRelationship] = field(default_factory=list)
    discovery_notes: list[str] = field(default_factory=list)


def declared_foreign_keys(con) -> list[FKRelationship]:
    if con.backend == "duckdb":
        return _declared_duckdb(con)
    return _declared_sqla(con)


def _declared_duckdb(con) -> list[FKRelationship]:
    con.query_count += 1
    rows = con._raw.execute(
        "SELECT table_name, constraint_column_names, referenced_table, "
        "referenced_column_names "
        "FROM duckdb_constraints() "
        "WHERE constraint_type = 'FOREIGN KEY' AND database_name = current_database()"
    ).fetchall()
    out: list[FKRelationship] = []
    for table, cols, ref_table, ref_cols in rows:
        if not ref_table:
            continue
        out.append(
            FKRelationship(
                from_table=_strip_schema(table),
                from_columns=[str(c) for c in (cols or [])],
                to_table=_strip_schema(str(ref_table)),
                to_columns=[str(c) for c in (ref_cols or [])],
                declared=True,
                confidence=1.0,
            )
        )
    return out


def _strip_schema(name: str) -> str:
    return str(name).split(".")[-1] if "." in str(name) else str(name)


def _declared_sqla(con) -> list[FKRelationship]:
    """information_schema FK metadata.

    MySQL has no separate schema (``?schema=`` selects the database in the
    URL), so the current database - ``DATABASE()`` - is always the filter.
    PostgreSQL binds a concrete schema (``public`` by default).
    """
    from sqlalchemy import text

    con.query_count += 1
    if con.backend == "mysql":
        rows = con._raw.execute(
            text(
                "SELECT table_name, column_name, referenced_table_name, "
                "referenced_column_name, constraint_name, ordinal_position "
                "FROM information_schema.key_column_usage "
                "WHERE referenced_table_name IS NOT NULL "
                "AND table_schema = DATABASE() "
                "ORDER BY constraint_name, ordinal_position"
            )
        ).fetchall()
    else:
        rows = con._raw.execute(
            text(
                "SELECT tc.table_name, kcu.column_name, ccu.table_name, "
                "ccu.column_name, tc.constraint_name, kcu.ordinal_position "
                "FROM information_schema.table_constraints tc "
                "JOIN information_schema.key_column_usage kcu "
                "ON tc.constraint_name = kcu.constraint_name "
                "AND tc.table_schema = kcu.table_schema "
                "JOIN information_schema.constraint_column_usage ccu "
                "ON ccu.constraint_name = tc.constraint_name "
                "AND ccu.table_schema = tc.table_schema "
                "WHERE tc.constraint_type = 'FOREIGN KEY' AND tc.table_schema = :schema "
                "ORDER BY tc.constraint_name, kcu.ordinal_position"
            ),
            {"schema": con.sql_schema},
        ).fetchall()

    grouped: dict[str, dict] = {}
    for table, column, to_table, to_column, cname, _pos in rows:
        entry = grouped.setdefault(
            str(cname),
            {"from_table": _strip_schema(str(table)), "from_columns": [],
             "to_table": _strip_schema(str(to_table)), "to_columns": []},
        )
        entry["from_columns"].append(str(column))
        entry["to_columns"].append(str(to_column))
    return [
        FKRelationship(
            from_table=e["from_table"], from_columns=e["from_columns"],
            to_table=e["to_table"], to_columns=e["to_columns"],
            declared=True, confidence=1.0,
        )
        for e in grouped.values()
    ]
