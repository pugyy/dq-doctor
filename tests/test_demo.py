from pathlib import Path

import pytest

from dqdoctor.demo import create_demo_db, list_tables


@pytest.fixture
def demo_db(tmp_path: Path):
    db_path = create_demo_db(tmp_path / "test.duckdb")
    assert db_path.exists()
    return db_path


def test_create_demo_db(demo_db: Path):
    assert demo_db.exists()
    assert demo_db.stat().st_size > 0


def test_list_tables(demo_db: Path):
    tables = list_tables(demo_db)
    assert "orders" in tables
    assert "users" in tables
    assert "products" in tables


def test_create_demo_db_idempotent(tmp_path: Path):
    db1 = create_demo_db(tmp_path / "test.duckdb")
    db2 = create_demo_db(tmp_path / "test.duckdb")
    assert db1 == db2
    tables = list_tables(db2)
    assert len(tables) == 3
