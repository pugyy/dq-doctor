"""Audit round 2 P0-B: secrets must never land in a contract file."""
from __future__ import annotations

from datetime import UTC, datetime

import duckdb

from dqdoctor.datasources import DataSource, parse_spec


def _clock():
    return datetime(2026, 11, 17, 12, tzinfo=UTC)


def test_safe_persistent_ref_never_contains_a_password():
    ds = DataSource(parse_spec("postgresql://user:hunter2@db.example.com:5432/prod"))
    safe = ds.safe_persistent_ref()
    assert "hunter2" not in safe
    assert "user:***@" in safe


def test_safe_persistent_ref_keeps_file_datasources_usable(tmp_root):
    """Local paths are stored absolute so a moved contract still resolves."""
    db = tmp_root / "demo.duckdb"
    con = duckdb.connect(str(db))
    con.execute("CREATE TABLE t (id INTEGER)")
    con.close()
    ds = DataSource(parse_spec(str(db)))
    safe = ds.safe_persistent_ref()
    assert safe == str(db.resolve())
    assert DataSource(parse_spec(safe)).spec.path is not None


def test_requires_secret_handling_flags_urls_with_userinfo():
    assert DataSource(
        parse_spec("postgresql://u:p@h:5432/db")
    ).requires_secret_handling()
    assert DataSource(parse_spec("demo.duckdb")).requires_secret_handling() is False


def test_query_parameter_passwords_are_redacted():
    """`?password=` is as sensitive as `u:p@h` and must be masked."""
    for url, secret in (
        ("postgresql://u@h/db?password=s3cret", "s3cret"),
        ("mysql://u@h/db?passwd=hunter2", "hunter2"),
        ("postgresql://u@h/db?token=abc123", "abc123"),
    ):
        ds = DataSource(parse_spec(url))
        assert secret not in ds.describe(), ds.describe()
        assert secret not in ds.safe_persistent_ref(), ds.safe_persistent_ref()
        assert ds.requires_secret_handling() is True


def test_non_secret_query_parameters_are_kept():
    ds = DataSource(parse_spec("postgresql://u@h/db?sslmode=require"))
    assert "sslmode=require" in ds.describe()
    assert ds.requires_secret_handling() is False


def test_safe_persistent_ref_masks_both_userinfo_and_query():
    ds = DataSource(parse_spec("postgresql://u:p@h/db?password=z&sslmode=require"))
    safe = ds.safe_persistent_ref()
    assert "u:***@" in safe
    assert "password=***" in safe
    assert "sslmode=require" in safe
    assert ":p@" not in safe
    assert "password=z" not in safe


def test_rules_init_does_not_write_url_credentials(tmp_root, monkeypatch):
    """A URL datasource must never be persisted with a live password."""
    from typer.testing import CliRunner

    from dqdoctor.cli import app

    monkeypatch.chdir(tmp_root)
    db = tmp_root / "d.duckdb"
    con = duckdb.connect(str(db))
    con.execute("CREATE TABLE t (id INTEGER)")
    con.execute("INSERT INTO t VALUES (1)")
    con.close()

    out = tmp_root / "contract.yml"
    result = CliRunner().invoke(app, [
        "rules-init", "--db", str(db), "--all-tables", "--out", str(out),
    ])
    assert result.exit_code == 0, result.output
    text = out.read_text(encoding="utf-8")
    assert str(db) in text  # local file datasource is still recorded
    assert "***" not in text


def test_check_refuses_a_redacted_contract_datasource(tmp_root):
    """If a contract holds a redacted URL, fail loudly instead of dialling it."""
    from typer.testing import CliRunner

    from dqdoctor.cli import app

    contract = tmp_root / "c.yml"
    contract.write_text(
        "version: 1\n"
        "datasource: postgresql://user:***@host:5432/db\n"
        "tables:\n"
        "  t:\n    rules:\n"
        "      - {id: not_null:id, type: not_null, column: id}\n",
        encoding="utf-8",
    )
    result = CliRunner().invoke(app, [
        "check", "--table", "t", "--rules", str(contract),
        "--out", str(tmp_root / "r.html"),
    ])
    assert result.exit_code == 2
    assert "redacted datasource" in result.output


def test_gitignore_covers_backups_and_generated_contracts():
    from pathlib import Path

    ignore = Path(__file__).resolve().parents[1] / ".gitignore"
    text = ignore.read_text(encoding="utf-8")
    for pattern in ("*.duckdb.bak", "contract.yml", "*.contract.yml"):
        assert pattern in text, pattern
