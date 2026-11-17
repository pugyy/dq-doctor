"""CLI command coverage and exporter edge cases (audit follow-up)."""
from __future__ import annotations

import json

import duckdb
import pytest
from typer.testing import CliRunner

from dqdoctor.cli import app


@pytest.fixture()
def demo_db(tmp_root, monkeypatch):
    monkeypatch.chdir(tmp_root)
    runner = CliRunner()
    result = runner.invoke(app, ["demo", "--dirty", "--output", "d.duckdb"])
    assert result.exit_code == 0, result.output
    return tmp_root / "d.duckdb"


def test_version_flag():
    result = CliRunner().invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "dq-doctor" in result.output


def test_doctor_command():
    result = CliRunner().invoke(app, ["doctor"])
    assert result.exit_code == 0
    assert "core checks passed" in result.output


def test_tables_command(demo_db, tmp_root, monkeypatch):
    monkeypatch.chdir(tmp_root)
    result = CliRunner().invoke(app, ["tables", "--db", str(demo_db)])
    assert result.exit_code == 0, result.output
    assert "dirty_orders" in result.output


def test_profile_command_and_json_output(demo_db, tmp_root, monkeypatch):
    monkeypatch.chdir(tmp_root)
    out = tmp_root / "p.json"
    result = CliRunner().invoke(app, [
        "profile", "--db", str(demo_db), "--table", "dirty_orders",
        "--out", str(out),
    ])
    assert result.exit_code == 0, result.output
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["table_name"] == "dirty_orders"
    assert "sample_values" not in data["columns"][0]


def test_profile_missing_table_exits_two(demo_db):
    result = CliRunner().invoke(app, [
        "profile", "--db", str(demo_db), "--table", "nope",
    ])
    assert result.exit_code == 2


def test_init_refuses_overwrite(tmp_root, monkeypatch):
    monkeypatch.chdir(tmp_root)
    runner = CliRunner()
    assert runner.invoke(app, ["init"]).exit_code == 0
    second = runner.invoke(app, ["init"])
    assert second.exit_code == 2
    assert "already exists" in second.output


def test_init_force_overwrites(tmp_root, monkeypatch):
    monkeypatch.chdir(tmp_root)
    runner = CliRunner()
    assert runner.invoke(app, ["init"]).exit_code == 0
    assert runner.invoke(app, ["init", "--force"]).exit_code == 0


def test_migrate_command(tmp_root):
    legacy = tmp_root / "legacy.yml"
    legacy.write_text(
        "table: t\nrules:\n"
        "  - {rule_id: not_null.id.3, rule_type: not_null, column: id}\n",
        encoding="utf-8",
    )
    out = tmp_root / "contract.yml"
    result = CliRunner().invoke(app, [
        "migrate", "--in", str(legacy), "--out", str(out),
    ])
    assert result.exit_code == 0, result.output
    assert "Migrated" in result.output
    assert out.exists()


def test_migrate_bad_file_exits_two(tmp_root):
    bad = tmp_root / "bad.yml"
    bad.write_text("nothing: here\n", encoding="utf-8")
    result = CliRunner().invoke(app, [
        "migrate", "--in", str(bad), "--out", str(tmp_root / "c.yml"),
    ])
    assert result.exit_code == 2


def test_export_all_formats(demo_db, tmp_root, monkeypatch):
    monkeypatch.chdir(tmp_root)
    runner = CliRunner()
    assert runner.invoke(app, [
        "rules-init", "--db", str(demo_db), "--all-tables", "--out", "c.yml",
    ]).exit_code == 0
    for fmt, name in (("dbt", "s.yml"), ("gx", "s.json"), ("soda", "s.yaml"),
                      ("deequ", "s.json"), ("markdown", "s.md")):
        result = runner.invoke(app, [
            "export", "--rules", "c.yml", "--format", fmt, "--out", name,
        ])
        assert result.exit_code == 0, (fmt, result.output)


def test_export_unknown_format_exits_two(demo_db, tmp_root, monkeypatch):
    monkeypatch.chdir(tmp_root)
    runner = CliRunner()
    runner.invoke(app, ["rules-init", "--db", str(demo_db), "--all-tables",
                        "--out", "c.yml"])
    result = runner.invoke(app, [
        "export", "--rules", "c.yml", "--format", "nope", "--out", "x.yml",
    ])
    assert result.exit_code == 2


def test_baseline_capture_and_use(demo_db, tmp_root, monkeypatch):
    monkeypatch.chdir(tmp_root)
    runner = CliRunner()
    assert runner.invoke(app, [
        "rules-init", "--db", str(demo_db), "--all-tables", "--out", "c.yml",
    ]).exit_code == 0
    cap = runner.invoke(app, [
        "baseline", "capture", "--db", str(demo_db), "--rules", "c.yml",
        "--out", "b.json",
    ])
    assert cap.exit_code == 0, cap.output
    data = json.loads((tmp_root / "b.json").read_text(encoding="utf-8"))
    assert "entries" in data

    run = runner.invoke(app, [
        "check", "--db", str(demo_db), "--all-tables", "--rules", "c.yml",
        "--baseline", "b.json", "--out", "r.html", "--ci",
    ])
    assert run.exit_code == 0, run.output


def test_baseline_bad_action_exits_two(tmp_root):
    result = CliRunner().invoke(app, ["baseline", "nope"])
    assert result.exit_code == 2


def test_drift_command(tmp_root):
    from dqdoctor.datasources import DataSource, parse_spec
    from dqdoctor.drift import save_profile
    from dqdoctor.profiling import profile_table

    old_path = tmp_root / "a.duckdb"
    con = duckdb.connect(str(old_path))
    con.execute("CREATE TABLE d (id INTEGER)")
    con.execute("INSERT INTO d VALUES (1)")
    con.close()

    new_path = tmp_root / "b.duckdb"
    con = duckdb.connect(str(new_path))
    con.execute("CREATE TABLE d (id INTEGER)")
    con.execute("INSERT INTO d VALUES (1), (2), (3), (4), (5)")
    con.close()

    snapshots = []
    for label, path in (("old", old_path), ("new", new_path)):
        ds = DataSource(parse_spec(str(path)))
        con = ds.open()
        try:
            snapshots.append(
                save_profile(profile_table(con, ds.describe(), "d"),
                             tmp_root / (label + ".json"))
            )
        finally:
            con.close()

    result = CliRunner().invoke(app, [
        "drift", "--old", str(snapshots[0]), "--new", str(snapshots[1]),
    ])
    assert result.exit_code == 0, result.output
    assert "drift" in result.output.lower()


def test_explore_check_without_db_and_config_exits_two(tmp_root, monkeypatch):
    monkeypatch.chdir(tmp_root)
    result = CliRunner().invoke(app, ["check", "--table", "t"])
    assert result.exit_code == 2
    assert "--db is required" in result.output


def test_invalid_fail_on_exits_two(demo_db):
    result = CliRunner().invoke(app, [
        "check", "--db", str(demo_db), "--table", "dirty_orders",
        "--fail-on", "critical",
    ])
    assert result.exit_code == 2
    assert "fail-on" in result.output


def test_missing_contract_exits_two(demo_db):
    result = CliRunner().invoke(app, [
        "check", "--db", str(demo_db), "--table", "dirty_orders",
        "--rules", "nope.yml",
    ])
    assert result.exit_code == 2
