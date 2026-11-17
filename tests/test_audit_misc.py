"""Audit P1 items: identifiers, contract scoping, outputs, demo, LLM."""
from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import duckdb
import pytest

from dqdoctor.contract import load_contract, migrate_legacy, save_contract
from dqdoctor.datasources import (
    DataSource,
    IdentifierError,
    parse_spec,
    validate_identifier,
)
from dqdoctor.engine import CheckEngine
from dqdoctor.redact import redact_scalar


def _clock():
    return datetime(2026, 11, 17, 12, tzinfo=UTC)


# --- P1-8 ----------------------------------------------------------------


def test_redaction_keeps_numbers_and_dates():
    assert redact_scalar(Decimal("12.50")) == Decimal("12.50")
    assert redact_scalar(date(2026, 1, 2)) == date(2026, 1, 2)
    assert redact_scalar(_clock()) == _clock()
    assert redact_scalar(42) == 42
    assert redact_scalar(1.5) == 1.5
    assert str(redact_scalar("secret@example.com")).startswith("<str:")


# --- P1-10 ---------------------------------------------------------------


def test_cjk_hyphen_and_digit_identifiers_are_allowed():
    assert validate_identifier("订单") == "订单"
    assert validate_identifier("order-items") == "order-items"
    assert validate_identifier("2024_sales") == "2024_sales"
    with pytest.raises(IdentifierError):
        validate_identifier("bad\x00name")


def test_cjk_table_profiles_end_to_end(tmp_root):
    path = tmp_root / "cjk.duckdb"
    con = duckdb.connect(str(path))
    con.execute('CREATE TABLE "订单" ("金额" INTEGER, "状态" VARCHAR)')
    con.execute("INSERT INTO \"订单\" VALUES (10, 'ok'), (20, 'ok')")
    con.close()
    outcome = CheckEngine(DataSource(parse_spec(str(path))), clock=_clock).run(
        tables=["订单"], explore=True
    )
    assert outcome.tables[0].profile.row_count == 2
    assert [c.name for c in outcome.tables[0].profile.columns] == ["金额", "状态"]


# --- P1-11 ---------------------------------------------------------------

MULTI_TABLE_CONTRACT = (
    "version: 1\n"
    "tables:\n"
    "  a:\n    rules:\n"
    "      - {id: not_null:id, type: not_null, column: id}\n"
    "  b:\n    rules:\n"
    "      - {id: not_null:id, type: not_null, column: id}\n"
)

LEGACY_MULTI = (
    "tables:\n"
    "  a:\n    sql_rules:\n"
    "      - {name: pos, query: 'SELECT COUNT(*) FROM a', expect: 0}\n"
    "  b:\n    sql_rules:\n"
    "      - {name: pos, query: 'SELECT COUNT(*) FROM b', expect: 0}\n"
)


def test_hand_written_multi_table_contract_loads(tmp_root):
    path = tmp_root / "multi.yml"
    path.write_text(MULTI_TABLE_CONTRACT, encoding="utf-8")
    ids = [r.id for tr in load_contract(path).tables.values() for r in tr.rules]
    assert ids == ["a/not_null:id", "b/not_null:id"]


def test_migrated_multi_table_contract_reloads(tmp_root):
    legacy = tmp_root / "legacy.yml"
    legacy.write_text(LEGACY_MULTI, encoding="utf-8")
    out = save_contract(migrate_legacy(legacy), tmp_root / "migrated.yml")
    ids = [r.id for tr in load_contract(out).tables.values() for r in tr.rules]
    assert ids == ["a/sql:pos", "b/sql:pos"]


# --- P1-14 ---------------------------------------------------------------


def test_init_default_alias_resolves_to_the_alias(tmp_root, monkeypatch):
    """`init` writes `default: demo`; resolve("") must use it, not ""."""
    monkeypatch.chdir(tmp_root)
    from typer.testing import CliRunner

    from dqdoctor.cli import app
    from dqdoctor.datasources import resolve

    assert CliRunner().invoke(app, ["init"]).exit_code == 0
    ds = resolve("", config_path=tmp_root / ".dqdoctor.yml")
    # the alias points at demo.duckdb; resolution must land there rather than
    # failing with "Empty datasource spec"
    assert ds.spec.path is not None
    assert ds.spec.path.name == "demo.duckdb"
    assert ds.kind == "duckdb"


# --- P1-15 ---------------------------------------------------------------


def test_demo_keeps_the_previous_database_as_backup(tmp_root):
    from dqdoctor import demo

    target = tmp_root / "keep.duckdb"
    target.write_bytes(b"original-bytes")
    demo.create_demo_db(str(target))
    assert (tmp_root / "keep.duckdb.bak").read_bytes() == b"original-bytes"
    assert target.stat().st_size > 100


# --- P1-17 ---------------------------------------------------------------


def test_junit_skipped_count_matches_elements(tmp_root):
    from xml.etree import ElementTree as ET

    from dqdoctor.contract import Contract, TableRules
    from dqdoctor.models import RuleSpec
    from dqdoctor.outputs import write_junit

    db = tmp_root / "j.duckdb"
    con = duckdb.connect(str(db))
    con.execute("CREATE TABLE j (id INTEGER)")
    con.execute("INSERT INTO j VALUES (1)")
    con.close()
    contract = Contract(tables={"j": TableRules(rules=[
        RuleSpec(id="nn:id", type="not_null", column="id", severity="high"),
        RuleSpec(id="bad", type="freshness", column="id",
                 params={"max_age_hours": 1}, severity="high"),
        RuleSpec(id="off", type="not_null", column="id", enabled=False),
    ])})
    outcome = CheckEngine(DataSource(parse_spec(str(db))), clock=_clock).run(
        tables=["j"], contract=contract
    )
    root = ET.parse(write_junit(outcome, tmp_root / "j.xml")).getroot()
    for suite in root:
        assert int(suite.get("skipped", "0")) == len(suite.findall(".//skipped"))


# --- P1-18 ---------------------------------------------------------------


def test_html_shows_column_profile_and_source(tmp_root):
    from dqdoctor.outputs import render_html

    db = tmp_root / "h.duckdb"
    con = duckdb.connect(str(db))
    con.execute("CREATE TABLE h (amount DECIMAL(10,2))")
    con.execute("INSERT INTO h VALUES (10.00), (20.00)")
    con.close()
    outcome = CheckEngine(DataSource(parse_spec(str(db))), clock=_clock).run(
        tables=["h"], explore=True
    )
    html = render_html(outcome)
    assert "Column profile" in html
    assert "amount" in html
    assert "Semantic" in html


# --- P1-19 ---------------------------------------------------------------


def test_llm_module_imports_and_sends_no_samples():
    from dqdoctor.llm import client

    assert hasattr(client, "suggest_rules_llm")
    prompt = client._build_prompt([])
    assert "sample_values" not in prompt
    assert "sample=" not in prompt


# --- P1-20 ---------------------------------------------------------------


def test_directory_source_with_duplicate_stems(tmp_root, monkeypatch):
    """users.csv + users.parquet in one directory must both register."""
    monkeypatch.chdir(tmp_root)
    (tmp_root / "users.csv").write_text("id,name\n1,a\n", encoding="utf-8")
    build = duckdb.connect()
    build.execute("COPY (SELECT 1 AS id) TO 'users.parquet' (FORMAT PARQUET)")
    build.close()

    ds = DataSource(parse_spec("."))
    names = ds.tables()
    assert len(names) == 2, names
    assert len(set(names)) == 2
    con = ds.open()
    try:
        from dqdoctor.queries import table_columns

        for name in names:
            assert table_columns(con, name)
    finally:
        con.close()
