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
    to_schema: str | None = None


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
    """Fetch FK metadata with each source column paired to its target column.

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
                "referenced_column_name, constraint_name, ordinal_position, "
                "referenced_table_schema, table_schema "
                "FROM information_schema.key_column_usage "
                "WHERE referenced_table_name IS NOT NULL "
                "AND table_schema = DATABASE() "
                "ORDER BY constraint_name, ordinal_position"
            )
        ).fetchall()
    else:
        rows = con._raw.execute(
            text(
                "SELECT src.relname, sa.attname, dst.relname, da.attname, "
                "fk.oid, key.ord, dn.nspname, sn.nspname "
                "FROM pg_catalog.pg_constraint fk "
                "JOIN pg_catalog.pg_class src ON src.oid = fk.conrelid "
                "JOIN pg_catalog.pg_class dst ON dst.oid = fk.confrelid "
                "JOIN pg_catalog.pg_namespace sn ON sn.oid = src.relnamespace "
                "JOIN pg_catalog.pg_namespace dn ON dn.oid = dst.relnamespace "
                "CROSS JOIN LATERAL unnest(fk.conkey, fk.confkey) "
                "WITH ORDINALITY AS key(source_num, target_num, ord) "
                "JOIN pg_catalog.pg_attribute sa "
                "ON sa.attrelid = src.oid AND sa.attnum = key.source_num "
                "JOIN pg_catalog.pg_attribute da "
                "ON da.attrelid = dst.oid AND da.attnum = key.target_num "
                "WHERE fk.contype = 'f' AND sn.nspname = :schema "
                "ORDER BY fk.oid, key.ord"
            ),
            {"schema": con.sql_schema},
        ).fetchall()

    grouped: dict[tuple[str, str], FKRelationship] = {}
    for table, column, to_table, to_column, cname, _pos, to_schema, from_schema in rows:
        entry = grouped.setdefault(
            (str(table), str(cname)),
            FKRelationship(
                from_table=str(table), from_columns=[],
                to_table=str(to_table), to_columns=[],
                to_schema=str(to_schema) if to_schema != from_schema else None,
            ),
        )
        entry.from_columns.append(str(column))
        entry.to_columns.append(str(to_column))
    return list(grouped.values())
