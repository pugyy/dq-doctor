"""Regression checks for release-blocking audit findings."""

import asyncio
import sys

import duckdb
import pytest
from typer.testing import CliRunner

from dqdoctor import baseline
from dqdoctor.cli import app
from dqdoctor.contract import Contract, TableRules, save_contract
from dqdoctor.datasources import DataSource, parse_spec
from dqdoctor.engine import CheckEngine
from dqdoctor.models import RuleSpec, RuleStatus
from dqdoctor.sqlpolicy import read_only_problem


@pytest.fixture
def audited_db(tmp_path):
    db = tmp_path / "audit.duckdb"
    with duckdb.connect(str(db)) as con:
        con.execute("CREATE TABLE items (status VARCHAR)")
        con.execute("INSERT INTO items VALUES ('bad')")
    return db


def _rule(db, spec):
    contract = Contract(tables={"items": TableRules(rules=[spec])})
    outcome = CheckEngine(DataSource(parse_spec(str(db)))).run(contract=contract)
    return outcome.tables[0].rule_results[0]


def test_null_in_accepted_set_does_not_hide_invalid_values(audited_db):
    result = _rule(audited_db, RuleSpec(
        id="status", type="accepted_values", column="status", params={"values": ["ok", None]},
    ))
    assert result.status is RuleStatus.FAIL
    assert result.failed_count == 1


def test_sql_rejects_more_than_one_row(audited_db):
    result = _rule(audited_db, RuleSpec(
        id="scalar", type="sql", column="*",
        params={"query": "VALUES (0), (1)", "expect": {"value": 0}},
    ))
    assert result.status is RuleStatus.ERROR
    assert "rows" in result.message


def test_check_all_detects_a_missing_contract_table(audited_db, tmp_path):
    rules = save_contract(Contract(tables={"missing": TableRules(rules=[
        RuleSpec(id="required", type="row_count", column="*", params={"min": 1}),
    ])}), tmp_path / "contract.yml")
    result = CliRunner().invoke(app, [
        "check", "--db", str(audited_db), "--all-tables", "--rules", str(rules),
        "--ci", "--out", str(tmp_path / "report.html"),
    ])
    assert result.exit_code == 2, result.output


def test_check_rejects_missing_explicit_config(audited_db, tmp_path):
    result = CliRunner().invoke(app, [
        "check", "--db", str(audited_db), "--table", "items", "--config",
        str(tmp_path / "missing.yml"), "--out", str(tmp_path / "report.html"),
    ])
    assert result.exit_code == 2
    assert "Config file not found" in result.output


def test_migrate_redacts_legacy_url(tmp_path):
    legacy = tmp_path / "legacy.yml"
    legacy.write_text(
        "table: items\ndb: postgresql://user:sentinel@host/db?password=sentinel\nrules: []\n",
        encoding="utf-8",
    )
    output = tmp_path / "contract.yml"
    result = CliRunner().invoke(app, ["migrate", "--in", str(legacy), "--out", str(output)])
    assert result.exit_code == 0, result.output
    assert "sentinel" not in output.read_text(encoding="utf-8")


def test_multi_table_report_names_do_not_collide(audited_db, tmp_path):
    with duckdb.connect(str(audited_db)) as con:
        con.execute('CREATE TABLE "x y" (id INTEGER)')
        con.execute('CREATE TABLE "x-y" (id INTEGER)')
        con.execute('CREATE TABLE "x_y" (id INTEGER)')
    result = CliRunner().invoke(app, [
        "check", "--db", str(audited_db), "--all-tables",
        "--out", str(tmp_path / "report.html"),
    ])
    assert result.exit_code == 0, result.output
    assert len(list(tmp_path.glob("report_*.html"))) == 4


@pytest.mark.parametrize("query", [
    """SELECT pg_catalog."pg_read_file"('sentinel.txt')""",
    """SELECT LOAD_FILE('sentinel.txt')""",
    """SELECT 1 INTO OUTFILE 'sentinel.txt'""",
    """SELECT 1 /*! INTO DUMPFILE 'sentinel.txt' */""",
])
def test_sql_file_operations_rejected(query):
    assert read_only_problem(query) is not None


@pytest.mark.parametrize("query", [
    "SELECT 'private@example.test'",
    "SELECT CAST('private@example.test' AS INTEGER)",
])
def test_sql_result_and_driver_error_do_not_leak_text(audited_db, query):
    result = _rule(audited_db, RuleSpec(
        id="scalar", type="sql", column="*",
        params={"query": query, "expect": {"value": 0}},
    ))
    assert result.status is RuleStatus.ERROR
    assert "private@example.test" not in result.message


def test_baseline_does_not_exempt_a_changed_rule(audited_db):
    engine = CheckEngine(DataSource(parse_spec(str(audited_db))))
    spec = RuleSpec(id="rows", type="row_count", column="*", params={"min": 2})
    contract = Contract(tables={"items": TableRules(rules=[spec])})
    known = baseline.capture(engine.run(contract=contract), "now")
    unchanged = engine.run(contract=contract, baseline=known)
    assert unchanged.tables[0].rule_results[0].exempted
    contract.tables["items"].rules[0].params["min"] = 3
    changed = engine.run(contract=contract, baseline=known)
    assert changed.non_exempt_failures


def test_mcp_stdio_honors_aliases_and_table_selection(audited_db, tmp_path):
    pytest.importorskip("mcp")
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    with duckdb.connect(str(audited_db)) as con:
        con.execute("CREATE TABLE other (id INTEGER)")
    config = tmp_path / "config.yml"
    config.write_text("datasources:\n  audit: audit.duckdb\n", encoding="utf-8")
    server = StdioServerParameters(
        command=sys.executable,
        args=["-m", "dqdoctor.cli", "mcp", "--config", str(config)],
    )

    async def exercise_server(errlog):
        async with stdio_client(server, errlog=errlog) as (reader, writer):
            async with ClientSession(reader, writer) as session:
                await session.initialize()
                datasets = await session.call_tool("list_datasets")
                assert datasets.structuredContent["datasources"] == ["audit"]
                profile = await session.call_tool("profile_table", {
                    "datasource": "audit", "table": "items",
                })
                assert not profile.isError
                result = await session.call_tool("run_check", {
                    "datasource": "audit", "table": "items",
                })
                assert not result.isError
                assert [t["table_name"] for t in result.structuredContent["tables"]] == ["items"]
                denied = await session.call_tool("profile_table", {
                    "datasource": str(audited_db), "table": "items",
                })
                assert denied.isError

    with (tmp_path / "mcp.stderr").open("w", encoding="utf-8") as errlog:
        asyncio.run(asyncio.wait_for(exercise_server(errlog), timeout=25))
