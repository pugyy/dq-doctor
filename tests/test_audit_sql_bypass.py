"""Audit round 2: SQL rule bypasses must be refused twice over.

1. ``sqlpolicy`` rejects them by shape.
2. Even if a statement reaches the driver, the SQL-rule connection is opened
   with DuckDB ``enable_external_access=false`` and the read fails at the
   engine level.
"""
from __future__ import annotations

import duckdb
import pytest

from dqdoctor.datasources import DataSource, parse_spec
from dqdoctor.sqlexec import run_operator_query
from dqdoctor.sqlpolicy import read_only_problem

BYPASSES = [
    "SELECT count(*) FROM query_table('x.parquet')",
    "SELECT * FROM glob('C:/Windows/*.ini')",
    "SELECT * FROM 'x.parquet'",
    "SELECT * FROM read_json_objects('x.json')",
    "SELECT * FROM read_parquet('x.parquet')",
    "SELECT pg_read_file('/etc/passwd')",
    "SELECT pg_read_binary_file('/etc/passwd')",
    "SELECT pg_ls_dir('/etc')",
    "SELECT LOAD_FILE('/etc/passwd')",
    "SELECT lo_import('/etc/passwd')",
    "SELECT * FROM delta_scan('/tmp/delta')",
]


@pytest.mark.parametrize("statement", BYPASSES)
def test_policy_rejects_bypass_shapes(statement):
    assert read_only_problem(statement) is not None


def test_policy_rejects_comment_hidden_second_statement():
    """A literal '--' must not comment out a following command."""
    assert read_only_problem("SELECT '--' ; DELETE FROM t") is not None
    assert read_only_problem("SELECT '/*' ; DROP TABLE t") is not None


def test_policy_rejects_dml_cte():
    assert read_only_problem(
        "WITH d AS (DELETE FROM t RETURNING *) SELECT COUNT(*) FROM d"
    ) is not None


def test_policy_allows_quoted_keyword_identifiers():
    """`"copy"` as a column name is data, not the COPY statement."""
    assert read_only_problem('SELECT "copy" FROM t') is None
    assert read_only_problem('SELECT "delete" FROM t') is None


def test_policy_allows_parenthesised_select():
    assert read_only_problem("(SELECT 1) UNION (SELECT 2)") is None


def test_policy_rejects_comment_only_statement():
    assert read_only_problem("-- nothing here") is not None


# --- engine-level restriction (defence in depth) -------------------------


@pytest.fixture()
def restricted_env(tmp_root):
    db = tmp_root / "d.duckdb"
    con = duckdb.connect(str(db))
    con.execute("CREATE TABLE t (v INTEGER)")
    con.execute("INSERT INTO t VALUES (1)")
    con.close()
    secret = tmp_root / "secret.parquet"
    con = duckdb.connect()
    con.execute("COPY (SELECT 'LEAKED' AS s) TO 'secret.parquet' (FORMAT PARQUET)")
    con.close()
    return db, secret


def test_restricted_connection_blocks_file_reads(restricted_env):
    """DuckDB files are always opened without external access."""
    db, secret = restricted_env
    ds = DataSource(parse_spec(str(db)))
    con = ds.open(read_only=True)
    try:
        # normal table access still works
        assert run_operator_query(con, "SELECT COUNT(*) FROM t", 5.0) == 1
        for statement in (
            "SELECT count(*) FROM query_table('" + str(secret).replace("\\", "/") + "')",
            "SELECT * FROM glob('C:/Windows/*.ini')",
            "SELECT * FROM '" + str(secret).replace("\\", "/") + "'",
        ):
            with pytest.raises(duckdb.PermissionException):
                run_operator_query(con, statement, 5.0)
    finally:
        con.close()


def test_unrestricted_connection_still_reads_datasource(restricted_env):
    """The main connection keeps access - it must read the datasource."""
    db, _ = restricted_env
    ds = DataSource(parse_spec(str(db)))
    con = ds.open(read_only=True)
    try:
        assert run_operator_query(con, "SELECT COUNT(*) FROM t", 5.0) == 1
    finally:
        con.close()


def test_engine_runs_sql_rules_on_restricted_connection(restricted_env):
    """A SQL rule reaching a forbidden path becomes an ERROR, not a leak."""
    from dqdoctor.contract import Contract, TableRules
    from dqdoctor.engine import CheckEngine
    from dqdoctor.models import RuleSpec, RuleStatus

    db, _ = restricted_env
    contract = Contract(tables={"t": TableRules(rules=[
        RuleSpec(id="sql:leak", type="sql", column="*",
                 params={"query": "SELECT * FROM glob('C:/Windows/*.ini')",
                         "expect": {"mode": "eq", "value": 0}},
                 severity="high"),
    ])})
    outcome = CheckEngine(DataSource(parse_spec(str(db)))).run(
        tables=["t"], contract=contract
    )
    result = outcome.tables[0].rule_results[0]
    assert result.status is RuleStatus.ERROR


def test_file_source_views_still_work(tmp_root):
    """Disabling external access on file sources would break their own
    views (DuckDB re-reads the file per query), so it is not done there."""
    (tmp_root / "data.csv").write_text("x\n1\n2\n", encoding="utf-8")
    ds = DataSource(parse_spec(str(tmp_root / "data.csv")))
    con = ds.open()
    try:
        assert run_operator_query(con, "SELECT COUNT(*) FROM data", 5.0) == 2
    finally:
        con.close()


FILE_SOURCE_BYPASSES = [
    "SELECT * FROM glob('C:/Windows/*.ini')",
    "SELECT * FROM query_table('x.parquet')",
    "SELECT * FROM 'x.parquet'",
    "SELECT * FROM read_csv_auto('x.csv')",
]


@pytest.mark.parametrize("statement", FILE_SOURCE_BYPASSES)
def test_file_source_sql_rules_are_refused(tmp_root, statement):
    """SQL rules are not executed on file datasources at all.

    The engine-level file-access block cannot apply there (views re-read the
    file per query), and a keyword policy provably misses shapes such as
    ``JOIN 'x.parquet'`` or ``parquet_metadata(...)``. Refusing the rule is
    the structural fix; the result is a SKIP with a remediation message.
    """
    from dqdoctor.contract import Contract, TableRules
    from dqdoctor.engine import CheckEngine
    from dqdoctor.models import RuleSpec, RuleStatus

    (tmp_root / "data.csv").write_text("x\n1\n", encoding="utf-8")
    ds = DataSource(parse_spec(str(tmp_root / "data.csv")))
    contract = Contract(tables={"data": TableRules(rules=[
        RuleSpec(id="sql:x", type="sql", column="*",
                 params={"query": statement, "expect": {"mode": "eq", "value": 0}},
                 severity="high"),
    ])})
    outcome = CheckEngine(ds).run(tables=["data"], contract=contract)
    result = outcome.tables[0].rule_results[0]
    assert result.status is RuleStatus.SKIP, result.message
    assert "not supported on file datasources" in result.message


JOIN_BYPASSES = [
    "SELECT count(*) FROM data JOIN '{target}' q ON true",
    "SELECT * FROM data, '{target}'",
    "SELECT * FROM parquet_metadata('{target}')",
    'SELECT * FROM "read_text"(\'{target}\')',
]


@pytest.mark.parametrize("template", JOIN_BYPASSES)
def test_file_source_join_bypasses_not_executed(tmp_root, template, monkeypatch):
    """The shapes that defeated the policy must not run on a file source."""
    from dqdoctor.contract import Contract, TableRules
    from dqdoctor.engine import CheckEngine
    from dqdoctor.models import RuleSpec, RuleStatus

    monkeypatch.chdir(tmp_root)
    (tmp_root / "data.csv").write_text("x\n1\n", encoding="utf-8")
    build = duckdb.connect()
    build.execute("COPY (SELECT 'LEAKED' AS s) TO 'p.parquet' (FORMAT PARQUET)")
    build.close()

    statement = template.format(target="p.parquet")
    ds = DataSource(parse_spec("data.csv"))
    contract = Contract(tables={"data": TableRules(rules=[
        RuleSpec(id="sql:x", type="sql", column="*",
                 params={"query": statement, "expect": {"mode": "eq", "value": 0}},
                 severity="high"),
    ])})
    outcome = CheckEngine(ds).run(tables=["data"], contract=contract)
    result = outcome.tables[0].rule_results[0]
    assert result.status is RuleStatus.SKIP, result.message
    assert "LEAKED" not in result.message


def test_policy_rejects_join_replacement_scans():
    """The policy refuses FROM/JOIN literal table sources and metadata readers."""
    for statement in (
        "SELECT count(*) FROM t JOIN '/tmp/p.parquet' q ON true",
        "SELECT * FROM '/tmp/p.parquet'",
        "SELECT * FROM parquet_metadata('/tmp/p.parquet')",
    ):
        assert read_only_problem(statement) is not None, statement


def test_policy_allows_comma_form_but_engine_blocks_it(tmp_root, monkeypatch):
    """The comma table form (`FROM t, 'x'`) is allowed by the policy on
    purpose - a comma branch rejected every function argument - and is
    stopped at the engine level instead on DuckDB datasources."""
    import duckdb as _duckdb
    import pytest as _pytest

    monkeypatch.chdir(tmp_root)
    db = tmp_root / "c.duckdb"
    con = _duckdb.connect(str(db))
    con.execute("CREATE TABLE t (v INTEGER)")
    con.execute("INSERT INTO t VALUES (1)")
    con.close()

    build = _duckdb.connect()
    build.execute("COPY (SELECT 'LEAKED' AS s) TO 'p.parquet' (FORMAT PARQUET)")
    build.close()

    statement = "SELECT count(*) FROM t, 'p.parquet'"
    assert read_only_problem(statement) is None, "policy deliberately allows commas"

    ds = DataSource(parse_spec(str(db)))
    con = ds.open()
    try:
        with _pytest.raises(_duckdb.PermissionException):
            run_operator_query(con, statement, 5.0)
    finally:
        con.close()
