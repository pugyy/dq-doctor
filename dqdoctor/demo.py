from __future__ import annotations

from pathlib import Path

import duckdb

from dqdoctor.connectors.auto import list_tables as _auto_list_tables

EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "examples"
DEFAULT_DB_PATH = EXAMPLES_DIR / "ecommerce" / "demo.duckdb"
SEED_SQL_PATH = EXAMPLES_DIR / "ecommerce" / "seed.sql"


def create_demo_db(db_path: "str | Path | None" = None) -> Path:
    db_path = Path(db_path) if db_path else DEFAULT_DB_PATH
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


def list_tables(db_path: "str | Path") -> list[str]:
    from dqdoctor.connectors.auto import get_connection
    con = get_connection(str(db_path), read_only=True)
    try:
        return _auto_list_tables(con)
    finally:
        con.close()
