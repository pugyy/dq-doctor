from __future__ import annotations

from typing import Any

from dqdoctor.connectors.duckdb import (
    get_connection as get_duckdb_connection,
)
from dqdoctor.connectors.duckdb import (
    get_table_columns as get_duckdb_columns,
)


def _is_duckdb(db: str) -> bool:
    return (
        db.endswith(".duckdb")
        or db.endswith(".db")
        or "://" not in db
    )


def _is_postgresql(db: str) -> bool:
    return db.startswith("postgresql://") or db.startswith("postgres://")


def _is_mysql(db: str) -> bool:
    return db.startswith("mysql://") or db.startswith("mysql+pymysql://")


def detect_backend(db: str) -> str:
    if _is_duckdb(db):
        return "duckdb"
    if _is_postgresql(db):
        return "postgresql"
    if _is_mysql(db):
        return "mysql"
    return "duckdb"


def get_connection(db: str, read_only: bool = True) -> Any:
    backend = detect_backend(db)
    if backend == "duckdb":
        return get_duckdb_connection(db, read_only=read_only)
    try:
        from sqlalchemy import create_engine
    except ImportError:
        raise ImportError(
            "SQLAlchemy is required for PostgreSQL/MySQL. "
            "Install with: pip install dq-doctor[sql]"
        )
    engine = create_engine(db)
    return engine.connect()


def get_table_columns(con: Any, table_name: str) -> list[dict]:
    backend = _detect_from_con(con)
    if backend == "duckdb":
        return get_duckdb_columns(con, table_name)

    from sqlalchemy import text
    rows = con.execute(
        text(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_name = :table ORDER BY ordinal_position"
        ),
        {"table": table_name},
    ).fetchall()
    return [{"name": r[0], "dtype": r[1]} for r in rows]


def _detect_from_con(con: Any) -> str:
    mod = type(con).__module__
    if "duckdb" in mod:
        return "duckdb"
    if "psycopg" in mod or "postgresql" in mod:
        return "postgresql"
    if "mysql" in mod or "pymysql" in mod:
        return "mysql"
    return "unknown"


def list_tables_sqlalchemy(db: str) -> list[str]:
    from sqlalchemy import create_engine, text
    engine = create_engine(db)
    with engine.connect() as con:
        rows = con.execute(
            text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public' ORDER BY table_name"
            )
        ).fetchall()
        return [r[0] for r in rows]
