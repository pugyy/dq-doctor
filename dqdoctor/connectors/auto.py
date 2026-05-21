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


class ConnectionWrapper:
    def __init__(self, raw_con: Any, backend: str):
        self._con = raw_con
        self.backend = backend

    def execute(self, sql: str, params: Any = None) -> Any:
        if self.backend == "duckdb":
            if params is not None:
                return self._con.execute(sql, params)
            return self._con.execute(sql)
        from sqlalchemy import text
        if params is not None:
            if isinstance(params, (list, tuple)):
                param_dict = {f"p{i}": v for i, v in enumerate(params)}
                for i in range(len(params)):
                    sql = sql.replace("?", f":p{i}", 1)
                return self._con.execute(text(sql), param_dict)
            return self._con.execute(text(sql), params)
        return self._con.execute(text(sql))

    def fetchone(self, sql: str, params: Any = None) -> tuple | None:
        result = self.execute(sql, params)
        if self.backend == "duckdb":
            return result.fetchone()
        row = result.fetchone()
        if row is None:
            return None
        return tuple(row)

    def fetchall(self, sql: str, params: Any = None) -> list[tuple]:
        result = self.execute(sql, params)
        if self.backend == "duckdb":
            return result.fetchall()
        return [tuple(r) for r in result.fetchall()]

    def quote(self, name: str) -> str:
        if self.backend == "mysql":
            escaped = name.replace("`", "``")
            return f"`{escaped}`"
        escaped = name.replace('"', '""')
        return f'"{escaped}"'

    def close(self) -> None:
        if self.backend == "duckdb":
            self._con.close()
        else:
            self._con.close()


def get_connection(db: str, read_only: bool = True) -> ConnectionWrapper:
    backend = detect_backend(db)
    if backend == "duckdb":
        raw = get_duckdb_connection(db, read_only=read_only)
        return ConnectionWrapper(raw, "duckdb")
    try:
        from sqlalchemy import create_engine
    except ImportError:
        raise ImportError(
            "SQLAlchemy is required for PostgreSQL/MySQL. "
            "Install with: pip install dq-doctor[sql]"
        )
    connect_args = {}
    if read_only and backend == "postgresql":
        connect_args["options"] = "-c default_transaction_read_only=on"
    engine = create_engine(db, connect_args=connect_args)
    raw = engine.connect()
    return ConnectionWrapper(raw, backend)


def get_table_columns(wrapped: ConnectionWrapper, table_name: str) -> list[dict]:
    if wrapped.backend == "duckdb":
        return get_duckdb_columns(wrapped._con, table_name)
    if wrapped.backend == "mysql":
        rows = wrapped.fetchall(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_schema = DATABASE() AND table_name = ? "
            "ORDER BY ordinal_position",
            [table_name],
        )
    else:
        rows = wrapped.fetchall(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = ? "
            "ORDER BY ordinal_position",
            [table_name],
        )
    return [{"name": r[0], "dtype": r[1]} for r in rows]


def list_tables(wrapped: ConnectionWrapper) -> list[str]:
    if wrapped.backend == "duckdb":
        rows = wrapped.fetchall(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'main' ORDER BY table_name"
        )
    elif wrapped.backend == "mysql":
        rows = wrapped.fetchall(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = DATABASE() ORDER BY table_name"
        )
    else:
        rows = wrapped.fetchall(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' ORDER BY table_name"
        )
    return [r[0] for r in rows]
