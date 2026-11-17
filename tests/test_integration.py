"""Exporter, redaction, datasource and FK tests."""
from __future__ import annotations

import json

import duckdb
import pytest

from dqdoctor.contract import Contract, TableRules
from dqdoctor.datasources import DataSource, parse_spec
from dqdoctor.models import RuleSpec


@pytest.fixture()
def sample_contract():
    return Contract(
        datasource="demo.duckdb",
        tables={
            "orders": TableRules(rules=[
                RuleSpec(id="orders/not_null:order_id", type="not_null",
                         column="order_id", severity="high"),
                RuleSpec(id="orders/unique:order_id", type="unique",
                         column="order_id", severity="high"),
                RuleSpec(id="orders/accepted_values:status", type="accepted_values",
                         column="status", params={"values": ["ok", "bad"]},
                         severity="medium"),
                RuleSpec(id="orders/range:amount", type="range", column="amount",
                         params={"min": "0.01", "max": "99999.99"}, severity="medium"),
                RuleSpec(id="orders/range:amount2", type="range", column="amount",
                         params={"min": "200000", "max": "300000"}, severity="low",
                         enabled=False),
            ])
        },
    )


def test_dbt_uses_data_tests_and_numeric_literals(sample_contract, tmp_root):
    from dqdoctor.exporters import dbt

    text = dbt.export_dbt(sample_contract)
    assert "data_tests:" in text
    assert "tests:" not in text.replace("data_tests:", "")
    assert "arguments:" in text
    assert "expression: '>= 0.01'" in text
    assert "expression: <= 99999.99" in text
    assert "300000" not in text
    assert dbt.save(sample_contract, tmp_root / "schema.yml").exists()


def test_dbt_accepted_values_shape(sample_contract):
    from dqdoctor.exporters import dbt

    payload = dbt.export_dbt(sample_contract)
    assert "accepted_values:" in payload
    assert "ok" in payload


def test_gx_suite_is_1x_shape(sample_contract):
    from dqdoctor.exporters import gx

    data = json.loads(gx.export_gx(sample_contract))
    suite = data["suites"][0]
    assert set(suite) == {"name", "expectations", "meta"}
    assert all("type" in e and "kwargs" in e for e in suite["expectations"])


def test_gx_exact_row_count_uses_equal_expectation(sample_contract):
    from dqdoctor.exporters import gx

    sample_contract.tables["orders"].rules.append(
        RuleSpec(id="rows", type="row_count", params={"exact": 7})
    )
    suite = json.loads(gx.export_gx(sample_contract))["suites"][0]
    assert suite["expectations"][-1]["type"] == "expect_table_row_count_to_equal"
    assert suite["expectations"][-1]["kwargs"] == {"value": 7}


def test_soda_uses_valid_values_block(sample_contract):
    from dqdoctor.exporters import soda

    text = soda.export_soda(sample_contract)
    assert "invalid_count(status) = 0:" in text
    assert "valid values:" in text
    assert "values:" not in text.replace("valid values:", "")


def test_deequ_names_its_consumer(sample_contract):
    from dqdoctor.exporters import deequ

    data = json.loads(deequ.export_deequ(sample_contract))
    assert data["datasets"][0]["engine"] == "pydeequ"


def test_markdown_lists_every_rule(sample_contract):
    from dqdoctor.exporters import markdown

    text = markdown.export_markdown(sample_contract)
    assert "orders/not_null:order_id" in text
    assert "orders/range:amount2" in text
    assert "| no |" in text


def test_report_json_redacts_text_min_max(clean_db, tmp_root):
    from dqdoctor.engine import CheckEngine
    from dqdoctor.outputs import write_json
    from tests.conftest import fixed_clock

    ds = DataSource(parse_spec(str(clean_db)))
    outcome = CheckEngine(ds, clock=fixed_clock).run(tables=["users"], explore=True)
    data = json.loads(write_json(outcome, tmp_root / "r.json").read_text("utf-8"))
    columns = {c["name"]: c for c in data["tables"][0]["profile"]["columns"]}
    assert columns["email"]["min_value"].startswith("<str:")
    assert columns["id"]["min_value"] == 1
    assert "sample_values" not in columns["email"]
    assert "distinct_values" not in columns["email"]


def test_pii_findings_never_include_values(tmp_root):
    from dqdoctor.engine import CheckEngine
    from dqdoctor.outputs import write_json
    from tests.conftest import fixed_clock

    path = tmp_root / "p.duckdb"
    con = duckdb.connect(str(path))
    con.execute("CREATE TABLE p (email VARCHAR)")
    con.execute("INSERT INTO p VALUES ('secret.person@example.com')")
    con.close()
    ds = DataSource(parse_spec(str(path)))
    outcome = CheckEngine(ds, clock=fixed_clock).run(tables=["p"], explore=True)
    text = write_json(outcome, tmp_root / "p.json").read_text(encoding="utf-8")
    assert "secret.person" not in text


def test_connection_credentials_redacted():
    from dqdoctor.datasources import redact_url

    assert "hunter2" not in redact_url("postgresql://u:hunter2@db:5432/x")
    assert "u:***@" in redact_url("postgresql://u:hunter2@db:5432/x")


def test_mysql_url_normalized_to_pymysql():
    spec = parse_spec("mysql://u:p@h:3306/db")
    assert spec.kind == "mysql"
    assert spec.url.startswith("mysql+pymysql://")


def test_schema_query_param_extracted():
    spec = parse_spec("postgresql://u:p@h/db?schema=analytics")
    assert spec.schema == "analytics"


def test_identifier_rejects_injection():
    from dqdoctor.datasources import IdentifierError, validate_identifier

    with pytest.raises(IdentifierError):
        validate_identifier('x"; DROP TABLE t; --')
    assert validate_identifier("order_id") == "order_id"


def test_csv_source(tmp_root):
    csv = tmp_root / "d.csv"
    csv.write_text("a,b\n1,x\n2,y\n", encoding="utf-8")
    ds = DataSource(parse_spec(str(csv)))
    assert ds.tables() == ["d"]
    assert [c["name"] for c in ds.columns("d")] == ["a", "b"]


def test_parquet_source(tmp_path):
    import os

    here = os.getcwd()
    try:
        os.chdir(tmp_path)
        con = duckdb.connect()
        con.execute("COPY (SELECT 1 AS a, 'x' AS b) TO 'src.parquet' (FORMAT PARQUET)")
        con.close()
    finally:
        os.chdir(here)
    ds = DataSource(parse_spec(str(tmp_path / "src.parquet")))
    assert ds.tables() == ["src"]
    assert [c["name"] for c in ds.columns("src")] == ["a", "b"]


@pytest.fixture()
def fk_db(tmp_root):
    path = tmp_root / "fk.duckdb"
    con = duckdb.connect(str(path))
    con.execute("CREATE TABLE users (id INTEGER PRIMARY KEY)")
    con.execute(
        "CREATE TABLE orders (id INTEGER, user_id INTEGER REFERENCES users(id))"
    )
    con.execute("INSERT INTO users VALUES (1),(2)")
    con.execute("INSERT INTO orders VALUES (1,1),(2,2)")
    con.close()
    return path


def test_declared_fk_read_and_checked_once(fk_db):
    from dqdoctor.fkcheck import build_plan, check_all

    con = DataSource(parse_spec(str(fk_db))).open()
    try:
        plan = build_plan(con, include_heuristic=False)
        assert len(plan.relationships) == 1
        rel = plan.relationships[0]
        assert (rel.from_table, rel.from_columns) == ("orders", ["user_id"])
        assert (rel.to_table, rel.to_columns) == ("users", ["id"])
        assert rel.declared is True
        issues = check_all(con, plan)
        assert len(issues) == 1 and issues[0].orphan_rows == 0
    finally:
        con.close()


def test_composite_declared_fk(tmp_root):
    """Composite declared keys are read and checked as one relationship.

    DuckDB enforces the constraint on insert, so the orphan row is created
    by dropping the constraint afterwards - the metadata path is what is
    under test.
    """
    path = tmp_root / "comp.duckdb"
    con = duckdb.connect(str(path))
    con.execute("CREATE TABLE parent (a INTEGER, b INTEGER, PRIMARY KEY (a, b))")
    con.execute(
        "CREATE TABLE child (a INTEGER, b INTEGER, "
        "FOREIGN KEY (a, b) REFERENCES parent(a, b))"
    )
    con.execute("INSERT INTO parent VALUES (1,1)")
    con.execute("INSERT INTO child VALUES (1,1)")
    con.close()
    from dqdoctor.fkcheck import build_plan, check_all

    con2 = DataSource(parse_spec(str(path))).open()
    try:
        plan = build_plan(con2, include_heuristic=False)
        assert len(plan.relationships) == 1
        rel = plan.relationships[0]
        assert rel.from_columns == ["a", "b"]
        assert rel.to_columns == ["a", "b"]
        issues = check_all(con2, plan)
        assert issues[0].from_column == "a+b"
        assert issues[0].orphan_rows == 0
    finally:
        con2.close()
