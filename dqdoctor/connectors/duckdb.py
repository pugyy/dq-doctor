from __future__ import annotations

from pathlib import Path

import duckdb


def get_connection(db_path: str | Path, read_only: bool = True) -> duckdb.DuckDBPyConnection:
    return duckdb.connect(str(db_path), read_only=read_only)


def get_table_columns(con: duckdb.DuckDBPyConnection, table_name: str) -> list[dict]:
    rows = con.execute(
        "SELECT column_name, data_type FROM information_schema.columns "
        "WHERE table_name = ? ORDER BY ordinal_position",
        [table_name],
    ).fetchall()
    return [{"name": r[0], "dtype": r[1]} for r in rows]
