"""Windows console encoding and contract-relative path regressions.

The CLI crashed *after* a successful check on a GBK console because Rich
rendered a rule id such as ``not_null:a`` with an emoji glyph, which GBK
cannot encode - turning a passing run into exit 1.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import duckdb
import pytest


def _run_cli(args, cwd, env_extra=None):
    env = dict(os.environ)
    env["NO_PROXY"] = "*"
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [sys.executable, "-m", "dqdoctor.cli", *args],
        cwd=str(cwd), capture_output=True, text=True, env=env, timeout=180,
    )


@pytest.fixture()
def short_name_db(tmp_root):
    """Column named ``a`` - the shape that used to render as an emoji."""
    path = tmp_root / "t.duckdb"
    con = duckdb.connect(str(path))
    con.execute("CREATE TABLE t (a INTEGER)")
    con.execute("INSERT INTO t VALUES (1)")
    con.close()
    return path


@pytest.mark.skipif(sys.platform != "win32", reason="GBK console is Windows-specific")
def test_gbk_console_does_not_crash_the_cli(short_name_db, tmp_root):
    result = _run_cli(
        ["check", "--db", str(short_name_db), "--table", "t",
         "--out", str(tmp_root / "r.html")],
        cwd=tmp_root,
        env_extra={"PYTHONIOENCODING": "gbk"},
    )
    assert result.returncode == 0, (result.returncode, result.stderr[-800:])
    assert "UnicodeEncodeError" not in result.stderr


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-specific")
def test_gbk_console_ci_mode_keeps_gate_semantics(short_name_db, tmp_root):
    """Encoding must not turn a passing gate into a non-zero exit."""
    result = _run_cli(
        ["check", "--db", str(short_name_db), "--table", "t",
         "--out", str(tmp_root / "r.html"), "--ci"],
        cwd=tmp_root,
        env_extra={"PYTHONIOENCODING": "gbk"},
    )
    # explore mode with no contract has nothing to gate; 0 expected
    assert result.returncode == 0, (result.returncode, result.stderr[-800:])


def test_contract_relative_path_resolves_from_contract_dir(tmp_root):
    """A contract in a subdirectory resolves its datasource next to itself."""
    sub = tmp_root / "contracts"
    sub.mkdir()
    db = sub / "data.duckdb"
    con = duckdb.connect(str(db))
    con.execute("CREATE TABLE t (a INTEGER)")
    con.execute("INSERT INTO t VALUES (1)")
    con.close()

    contract = sub / "c.yml"
    contract.write_text(
        "version: 1\n"
        "datasource: data.duckdb\n"
        "tables:\n"
        "  t:\n    rules:\n"
        "      - {id: not_null:a, type: not_null, column: a}\n",
        encoding="utf-8",
    )

    result = _run_cli(
        ["check", "--table", "t", "--rules", str(contract),
         "--out", str(tmp_root / "r.html")],
        cwd=tmp_root,  # deliberately NOT the contract directory
    )
    assert result.returncode == 0, (result.returncode, result.stdout[-600:])
    assert "database not found" not in result.stderr.lower()


def test_rules_init_stores_absolute_path(tmp_root, monkeypatch):
    """A generated contract keeps working when the cwd changes."""
    monkeypatch.chdir(tmp_root)
    db = tmp_root / "d.duckdb"
    con = duckdb.connect(str(db))
    con.execute("CREATE TABLE t (a INTEGER)")
    con.execute("INSERT INTO t VALUES (1)")
    con.close()

    from typer.testing import CliRunner

    from dqdoctor.cli import app
    from dqdoctor.contract import load_contract

    out = tmp_root / "c.yml"
    result = CliRunner().invoke(app, [
        "rules-init", "--db", "d.duckdb", "--all-tables", "--out", str(out),
    ])
    assert result.exit_code == 0, result.output
    datasource = load_contract(out).datasource
    assert datasource is not None
    assert Path(datasource).is_absolute(), datasource
