"""Performance guard: profiling cost must not scale with column count."""
from __future__ import annotations

import duckdb

from dqdoctor.datasources import DataSource, parse_spec
from dqdoctor.profiling import profile_table


def test_wide_table_profile_stays_batched(tmp_root):
    """A 40-column table must not cost many more queries than a 5-column one."""
    narrow_path = tmp_root / "w5.duckdb"
    con = duckdb.connect(str(narrow_path))
    con.execute(
        "CREATE TABLE wide (c0 INTEGER, c1 INTEGER, c2 INTEGER, c3 INTEGER,"
        " c4 INTEGER)"
    )
    con.execute("INSERT INTO wide VALUES (0,1,2,3,4)")
    con.close()

    wide_path = tmp_root / "w40.duckdb"
    con = duckdb.connect(str(wide_path))
    con.execute(
        "CREATE TABLE wide (c0 INTEGER, c1 INTEGER, c2 INTEGER, c3 INTEGER,"
        " c4 INTEGER, c5 INTEGER, c6 INTEGER, c7 INTEGER, c8 INTEGER,"
        " c9 INTEGER, c10 INTEGER, c11 INTEGER, c12 INTEGER, c13 INTEGER,"
        " c14 INTEGER, c15 INTEGER, c16 INTEGER, c17 INTEGER, c18 INTEGER,"
        " c19 INTEGER, c20 INTEGER, c21 INTEGER, c22 INTEGER, c23 INTEGER,"
        " c24 INTEGER, c25 INTEGER, c26 INTEGER, c27 INTEGER, c28 INTEGER,"
        " c29 INTEGER, c30 INTEGER, c31 INTEGER, c32 INTEGER, c33 INTEGER,"
        " c34 INTEGER, c35 INTEGER, c36 INTEGER, c37 INTEGER, c38 INTEGER,"
        " c39 INTEGER)"
    )
    con.execute(
        "INSERT INTO wide VALUES (0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,"
        "20,21,22,23,24,25,26,27,28,29,30,31,32,33,34,35,36,37,38,39)"
    )
    con.close()

    counts = {}
    for label, path in (("narrow", narrow_path), ("wide", wide_path)):
        ds = DataSource(parse_spec(str(path)))
        connection = ds.open()
        try:
            profile_table(connection, ds.describe(), "wide")
            counts[label] = connection.query_count
        finally:
            connection.close()

    assert counts["wide"] <= 12, f"40-column profile took {counts['wide']} queries"
    assert counts["wide"] - counts["narrow"] <= 8, counts


def test_million_row_profile_is_batched(tmp_root):
    path = tmp_root / "big.duckdb"
    con = duckdb.connect(str(path))
    con.execute(
        "CREATE TABLE big (id INTEGER, amount DECIMAL(10,2), status VARCHAR,"
        " ts TIMESTAMP)"
    )
    con.execute(
        "INSERT INTO big SELECT range, range * 1.5, 'ok',"
        " TIMESTAMP '2026-11-17 10:00:00' FROM range(1000000)"
    )
    con.close()
    ds = DataSource(parse_spec(str(path)))
    connection = ds.open()
    try:
        profile = profile_table(connection, ds.describe(), "big")
        assert profile.row_count == 1_000_000
        assert connection.query_count <= 12, connection.query_count
    finally:
        connection.close()
