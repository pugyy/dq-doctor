from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

from dqdoctor.connectors.auto import ConnectionWrapper, detect_backend


def test_detect_backend_duckdb():
    assert detect_backend("test.duckdb") == "duckdb"
    assert detect_backend("test.db") == "duckdb"
    assert detect_backend("/path/to/my.db") == "duckdb"


def test_detect_backend_postgresql():
    assert detect_backend("postgresql://user:pass@host/db") == "postgresql"
    assert detect_backend("postgres://user:pass@host/db") == "postgresql"


def test_detect_backend_mysql():
    assert detect_backend("mysql://user:pass@host/db") == "mysql"
    assert detect_backend("mysql+pymysql://user:pass@host/db") == "mysql"


def test_quote_duckdb_simple():
    con = ConnectionWrapper(MagicMock(), "duckdb")
    assert con.quote("order_id") == '"order_id"'


def test_quote_duckdb_escape():
    con = ConnectionWrapper(MagicMock(), "duckdb")
    assert con.quote('odd"name') == '"odd""name"'


def test_quote_mysql_simple():
    con = ConnectionWrapper(MagicMock(), "mysql")
    assert con.quote("order_id") == "`order_id`"


def test_quote_mysql_escape():
    con = ConnectionWrapper(MagicMock(), "mysql")
    assert con.quote("odd`name") == "`odd``name`"


def test_quote_postgresql_escape():
    con = ConnectionWrapper(MagicMock(), "postgresql")
    assert con.quote('col"name') == '"col""name"'


def test_fetchone_duckdb():
    mock_con = MagicMock()
    mock_result = MagicMock()
    mock_result.fetchone.return_value = (42,)
    mock_con.execute.return_value = mock_result
    con = ConnectionWrapper(mock_con, "duckdb")
    row = con.fetchone("SELECT COUNT(*) FROM t")
    assert row == (42,)


def test_fetchone_sqlalchemy():
    mock_text = MagicMock()
    mock_text.return_value = "wrapped_sql"

    mock_sa_result = MagicMock()
    mock_row = MagicMock()
    mock_row.__iter__ = lambda self: iter([42])
    mock_sa_result.fetchone.return_value = mock_row

    mock_con = MagicMock()
    mock_con.execute.return_value = mock_sa_result

    mock_sa = MagicMock()
    mock_sa.text = mock_text

    with patch.dict(sys.modules, {"sqlalchemy": mock_sa}):
        con = ConnectionWrapper(mock_con, "postgresql")
        row = con.fetchone("SELECT COUNT(*) FROM t")
        assert row == (42,)
