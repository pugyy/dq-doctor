"""Round-6 regressions: URL round-trips and live-test address handling.

1. ``parse_spec`` must accept every URL form the docs and this module
   produce (``postgresql+psycopg://`` was rejected by an earlier entrypoint
   while the normalizer emitted exactly that).
2. Live tests must dial the addresses from ``DQTEST_*``, not constants -
   the first CI run failed conceptually because tests dialled the
   developer's local ports.
"""
from __future__ import annotations

import socket
import time
from unittest.mock import patch

import pytest

from dqdoctor.datasources import DataSource, DatasourceError, parse_spec

PG_FORMS = [
    "postgresql://u:p@h/db",
    "postgres://u:p@h/db",
    "postgresql+psycopg://u:p@h/db",
    "postgres+psycopg://u:p@h/db",
    "postgresql+psycopg2://u:p@h/db",
]


@pytest.mark.parametrize("form", PG_FORMS)
def test_every_postgres_form_normalizes_and_round_trips(form):
    spec = parse_spec(form)
    assert spec.kind == "postgresql"
    assert spec.url.startswith("postgresql+psycopg://")
    # feeding the normalized URL back in is stable (contract round-trip)
    again = parse_spec(spec.url)
    assert again.url == spec.url


def test_mysql_forms_normalize():
    assert parse_spec("mysql://u@h/db").url.startswith("mysql+pymysql://")
    assert parse_spec(
        "mysql+pymysql://u@h/db"
    ).url == parse_spec("mysql://u@h/db").url


def test_unknown_scheme_rejected():
    with pytest.raises(DatasourceError):
        parse_spec("oracle://u@h/db")


@pytest.mark.parametrize("scheme", ["postgresql", "mysql"])
@pytest.mark.parametrize(("query", "env", "expected"), [
    ("", None, 10),
    ("", "2", 2),
    ("?password=contains_connect_timeout", None, 10),
    ("?connect%5Ftimeout=3", "invalid-but-overridden", None),
])
def test_connect_timeout_precedence(monkeypatch, scheme, query, env, expected):
    monkeypatch.delenv("DQ_CONNECT_TIMEOUT", raising=False)
    if env is not None:
        monkeypatch.setenv("DQ_CONNECT_TIMEOUT", env)
    ds = DataSource(parse_spec(f"{scheme}://x:x@localhost/db{query}"))
    with patch("sqlalchemy.create_engine") as create_engine:
        ds.open().close()
    assert create_engine.call_args.kwargs["connect_args"].get("connect_timeout") == expected
    if expected is None:
        assert create_engine.call_args.args[0].query["connect_timeout"] == "3"


def test_default_connect_timeout_bounds_stalled_postgres_handshake(monkeypatch):
    monkeypatch.delenv("DQ_CONNECT_TIMEOUT", raising=False)
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        port = listener.getsockname()[1]
        ds = DataSource(parse_spec(f"postgresql://x:x@127.0.0.1:{port}/db"))
        started = time.monotonic()
        with pytest.raises(DatasourceError, match="Could not connect"):
            ds.open()
        elapsed = time.monotonic() - started
    assert 8 < elapsed < 20
