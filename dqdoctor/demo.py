from __future__ import annotations

from pathlib import Path

import duckdb

from dqdoctor.datasources import Connection as _Connection

_DATA_DIR = Path(__file__).resolve().parent / "data"
SEED_SQL_PATH = _DATA_DIR / "seed.sql"
DIRTY_SEED_PATH = _DATA_DIR / "dirty_seed.sql"


def create_demo_db(db_path: "str | Path | None" = None) -> Path:
    db_path = Path(db_path) if db_path else Path("demo.duckdb")
    db_path.parent.mkdir(parents=True, exist_ok=True)

    if db_path.exists():
        db_path.unlink()

    seed_sql = SEED_SQL_PATH.read_text(encoding="utf-8")

    con = duckdb.connect(str(db_path))
    try:
        con.execute(seed_sql)
    finally:
        con.close()

    return db_path


def create_dirty_db(db_path: "str | Path | None" = None) -> Path:
    db_path = Path(db_path) if db_path else Path("dirty.duckdb")
    db_path.parent.mkdir(parents=True, exist_ok=True)

    if db_path.exists():
        db_path.unlink()

    seed_sql = DIRTY_SEED_PATH.read_text(encoding="utf-8")

    con = duckdb.connect(str(db_path))
    try:
        con.execute(seed_sql)
    finally:
        con.close()

    return db_path


def list_tables(db_path: "str | Path") -> list[str]:
    from dqdoctor.queries import list_tables as _list

    ds_path = Path(db_path)
    if not ds_path.exists():
        raise FileNotFoundError(f"DuckDB database not found: {ds_path}")
    con = _Connection(
        __import__("duckdb").connect(str(ds_path), read_only=True), "duckdb"
    )
    try:
        return _list(con)
    finally:
        con.close()
