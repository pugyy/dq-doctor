from pathlib import Path

import pytest
from typer.testing import CliRunner

from dqdoctor.cli import app
from dqdoctor.demo import create_demo_db

runner = CliRunner()


@pytest.fixture
def demo_db(tmp_path: Path):
    return create_demo_db(tmp_path / "test.duckdb")


def test_demo_command(tmp_path: Path):
    result = runner.invoke(app, ["demo", "--output", str(tmp_path / "demo.duckdb")])
    assert result.exit_code == 0
    assert "Demo database created" in result.stdout
    assert (tmp_path / "demo.duckdb").exists()


def test_tables_command(demo_db: Path):
    result = runner.invoke(app, ["tables", "--db", str(demo_db)])
    assert result.exit_code == 0
    assert "orders" in result.stdout
    assert "users" in result.stdout
    assert "products" in result.stdout


def test_profile_command(demo_db: Path):
    out_json = demo_db.parent / "profile.json"
    result = runner.invoke(app, [
        "profile", "--db", str(demo_db),
        "--table", "orders", "--out", str(out_json),
    ])
    assert result.exit_code == 0
    assert "order_id" in result.stdout
    assert out_json.exists()


def test_check_command(demo_db: Path):
    out_html = demo_db.parent / "report.html"
    result = runner.invoke(app, [
        "check", "--db", str(demo_db),
        "--table", "orders", "--out", str(out_html),
    ])
    assert result.exit_code == 0
    assert "PASS" in result.stdout
    assert out_html.exists()


def test_check_all_tables(demo_db: Path):
    out_dir = demo_db.parent
    result = runner.invoke(app, [
        "check", "--db", str(demo_db),
        "--all-tables", "--out", str(out_dir / "report.html"),
    ])
    assert result.exit_code == 0
    assert (out_dir / "report_orders.html").exists()
    assert (out_dir / "report_users.html").exists()
    assert (out_dir / "report_products.html").exists()


def test_check_requires_table_or_all(demo_db: Path):
    result = runner.invoke(app, ["check", "--db", str(demo_db)])
    assert result.exit_code != 0


def test_help():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "demo" in result.stdout
    assert "tables" in result.stdout
    assert "profile" in result.stdout
    assert "check" in result.stdout
