from __future__ import annotations

from pathlib import Path

import duckdb

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
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        rows = con.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'main' ORDER BY table_name"
        ).fetchall()
        return [r[0] for r in rows]
    finally:
        con.close()
