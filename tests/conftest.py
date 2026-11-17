"""Shared fixtures for the dq-doctor 1.0 test suite."""
from __future__ import annotations

import sys
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import duckdb
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dqdoctor.datasources import DataSource, parse_spec  # noqa: E402
from dqdoctor.engine import CheckEngine  # noqa: E402

FIXED_NOW = datetime(2026, 11, 17, 12, 0, 0, tzinfo=UTC)


def fixed_clock() -> datetime:
    """Injected clock: no test depends on the wall clock."""
    return FIXED_NOW


@pytest.fixture()
def tmp_root():
    return Path(tempfile.mkdtemp(prefix="dqtest-"))


@pytest.fixture()
def clean_db(tmp_root):
    """Reference batch: clean, contract-ready."""
    path = tmp_root / "clean.duckdb"
    con = duckdb.connect(str(path))
    con.execute(
        """
        CREATE TABLE users (id INTEGER PRIMARY KEY, email VARCHAR);
        CREATE TABLE orders (
            order_id INTEGER PRIMARY KEY,
            user_id INTEGER REFERENCES users(id),
            status VARCHAR,
            total_amount DECIMAL(10,2),
            created_at TIMESTAMP
        );
        INSERT INTO users VALUES (1, 'a@x.com'), (2, 'b@x.com');
        INSERT INTO orders VALUES
            (1, 1, 'ok', 10.00, '2026-11-17 10:00:00'),
            (2, 2, 'ok', 20.00, '2026-11-17 09:00:00'),
            (3, 1, 'ok', 30.00, '2026-11-17 08:00:00');
        """
    )
    con.close()
    return path


@pytest.fixture()
def dirty_batch(tmp_root):
    """New batch with fresh anomalies (orphans, bad status, negative amount)."""
    path = tmp_root / "dirty_batch.duckdb"
    con = duckdb.connect(str(path))
    con.execute(
        """
        CREATE TABLE users (id INTEGER, email VARCHAR);
        CREATE TABLE orders (
            order_id INTEGER, user_id INTEGER, status VARCHAR,
            total_amount DECIMAL(10,2), created_at TIMESTAMP
        );
        INSERT INTO users VALUES (1, 'a@x.com'), (2, 'b@x.com');
        INSERT INTO orders VALUES
            (1, 1, 'ok', 10.00, '2026-11-17 10:00:00'),
            (2, 2, 'weird', -5.00, '2026-11-17 09:00:00'),
            (3, 99, 'ok', 30.00, '2026-11-17 08:00:00'),
            (4, NULL, 'ok', 40.00, '2026-11-17 07:00:00');
        """
    )
    con.close()
    return path


@pytest.fixture()
def ds_clean(clean_db):
    return DataSource(parse_spec(str(clean_db)))


@pytest.fixture()
def engine(ds_clean):
    return CheckEngine(ds_clean, clock=fixed_clock)


def make_timestamp_value(con, table, column, value):
    con.execute(f"UPDATE {table} SET {column} = ?", [value])


@pytest.fixture()
def fresh_ts():
    return FIXED_NOW - timedelta(hours=2)


@pytest.fixture()
def stale_ts():
    return FIXED_NOW - timedelta(hours=48)


@pytest.fixture()
def future_ts():
    return FIXED_NOW + timedelta(hours=5)
