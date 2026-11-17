"""Regressions found by running against live MySQL 9.5 and PostgreSQL 16.

Both bugs were invisible to DuckDB-only testing:

1. MySQL declared-FK discovery bound ``None`` into ``table_schema = :schema``
   (the default-database case sets ``mysql_schema = None``), so no FK was
   ever found.
2. ``DataSource.open(read_only=False)`` still forced a read-only PostgreSQL
   session because the flag was hardcoded in ``connect_args``; fixtures and
   maintenance tooling then could not even DROP a table.

Set ``DQ_LIVE_REQUIRED=1`` to turn unreachable servers into failures (CI):
a green skip on a broken service hides exactly the regressions this file
exists to catch. Only *connectivity* errors skip - a driver bug or an
assertion raised during the probe fails loudly instead.
"""
from __future__ import annotations

import os

import pytest
from sqlalchemy.exc import OperationalError

from dqdoctor.datasources import DatasourceError, resolve


def _live(url_env: str, url: str):
    try:
        ds = resolve(url)
        con = ds.open()
    except (OperationalError, DatasourceError) as exc:
        if os.environ.get("DQ_LIVE_REQUIRED"):
            pytest.fail(f"{url_env} required but unreachable: {exc}")
        pytest.skip(f"{url_env} not reachable: {exc}")
    con.close()
    return ds


MYSQL_URL = "mysql://dqtest:dqtest@127.0.0.1:13306/dqtest"
PG_URL = "postgresql://postgres:@127.0.0.1:3361/dqtest"


def test_mysql_declared_fk_uses_current_database():
    """Default-database MySQL must still find declared foreign keys."""
    ds = _live("DQTEST_MYSQL", MYSQL_URL)
    # a plain URL has no ?schema=, so mysql_schema is None
    assert ds.spec.schema is None or ds.spec.schema == "dqtest"

    con = ds.open(read_only=False)
    from sqlalchemy import text  # noqa: F401

    try:
        con._raw.exec_driver_sql("DROP TABLE IF EXISTS fk_child")
        con._raw.exec_driver_sql("DROP TABLE IF EXISTS fk_parent")
        con._raw.exec_driver_sql(
            "CREATE TABLE fk_parent (id INTEGER PRIMARY KEY)"
        )
        con._raw.exec_driver_sql(
            "CREATE TABLE fk_child (id INTEGER PRIMARY KEY, parent_id INTEGER, "
            "FOREIGN KEY (parent_id) REFERENCES fk_parent(id))"
        )
        con._raw.commit()
    finally:
        con.close()

    from dqdoctor.fkdeclared import declared_foreign_keys

    con = ds.open()
    try:
        relationships = declared_foreign_keys(con)
    finally:
        con.close()
    matching = [r for r in relationships if r.from_table == "fk_child"]
    assert matching, "MySQL declared FK not discovered (schema binding bug)"
    assert matching[0].from_columns == ["parent_id"]
    assert matching[0].to_table == "fk_parent"
    assert matching[0].to_columns == ["id"]


def test_mysql_declared_fk_with_explicit_schema():
    """The explicit-database form uses the bound parameter path."""
    ds = _live("DQTEST_MYSQL", MYSQL_URL + "?schema=dqtest")
    con = ds.open(read_only=False)
    try:
        con._raw.exec_driver_sql(
            "CREATE TABLE IF NOT EXISTS fk_child2 (id INTEGER PRIMARY KEY, "
            "parent_id INTEGER, "
            "FOREIGN KEY (parent_id) REFERENCES fk_parent(id))"
        )
        con._raw.commit()
    finally:
        con.close()

    from dqdoctor.fkdeclared import declared_foreign_keys

    con = ds.open()
    try:
        relationships = declared_foreign_keys(con)
    finally:
        con.close()
    assert any(r.from_table == "fk_child2" for r in relationships)


def test_postgres_read_only_false_allows_ddl():
    """`open(read_only=False)` must actually be writable on PostgreSQL."""
    ds = _live("DQTEST_PG", PG_URL)
    con = ds.open(read_only=False)
    try:
        con._raw.exec_driver_sql("DROP TABLE IF EXISTS rw_probe")
        con._raw.exec_driver_sql("CREATE TABLE rw_probe (v INTEGER)")
        con._raw.commit()
    finally:
        con.close()


def test_postgres_read_only_true_blocks_ddl():
    from sqlalchemy.exc import InternalError as SAInternalError

    ds = _live("DQTEST_PG", PG_URL)
    con = ds.open(read_only=True)
    try:
        with pytest.raises(SAInternalError):
            con._raw.exec_driver_sql("CREATE TABLE should_not_exist (v INTEGER)")
    finally:
        con._raw.rollback()
        con.close()


def test_mysql_read_only_true_blocks_writes():
    from sqlalchemy.exc import OperationalError as SAOperationalError

    ds = _live("DQTEST_MYSQL", MYSQL_URL)
    con = ds.open(read_only=True)
    try:
        with pytest.raises(SAOperationalError):
            con._raw.exec_driver_sql("CREATE TABLE should_not_exist (v INTEGER)")
    finally:
        con._raw.rollback()
        con.close()


def test_engine_enforces_read_only_even_if_open_is_writable():
    """The check engine sets the session flag itself (belt and braces)."""
    ds = _live("DQTEST_PG", PG_URL)
    from dqdoctor.contract import Contract, TableRules
    from dqdoctor.engine import CheckEngine
    from dqdoctor.models import RuleSpec, RuleStatus

    con = ds.open(read_only=False)
    try:
        con._raw.exec_driver_sql("DROP TABLE IF EXISTS ro_orders")
        con._raw.exec_driver_sql(
            "CREATE TABLE ro_orders (id INTEGER, amount INTEGER)"
        )
        con._raw.exec_driver_sql("INSERT INTO ro_orders VALUES (1, 5)")
        con._raw.commit()
    finally:
        con.close()

    contract = Contract(tables={"ro_orders": TableRules(rules=[
        RuleSpec(id="sql:write", type="sql", column="*",
                 params={"query": "DELETE FROM ro_orders",
                         "expect": {"mode": "eq", "value": 0}},
                 severity="high"),
    ])})
    outcome = CheckEngine(ds).run(tables=["ro_orders"], contract=contract)
    assert outcome.tables[0].rule_results[0].status is RuleStatus.ERROR

    con = ds.open()
    try:
        row = con._raw.exec_driver_sql(
            "SELECT COUNT(*) FROM ro_orders"
        ).fetchone()
    finally:
        con.close()
    assert row[0] == 1, "row was deleted despite the read-only guard"
