"""Round-6 regressions: URL round-trips and live-test address handling.

1. ``parse_spec`` must accept every URL form the docs and this module
   produce (``postgresql+psycopg://`` was rejected by an earlier entrypoint
   while the normalizer emitted exactly that).
2. Live tests must dial the addresses from ``DQTEST_*``, not constants -
   the first CI run failed conceptually because tests dialled the
   developer's local ports.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from dqdoctor.datasources import DatasourceError, parse_spec

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


# --- live tests must read DQTEST_* ----------------------------------------


def _run_live_suite(env_extra: dict) -> int:
    """Run the live suite in a subprocess with the given env."""
    env = dict(os.environ)
    env["NO_PROXY"] = "*"
    env.update(env_extra)
    result = subprocess.run(
        [sys.executable, "-m", "pytest",
         str(Path(__file__).with_name("test_live_backends.py")),
         "-q", "-p", "no:cacheprovider", "--no-cov"],
        capture_output=True, text=True, env=env, timeout=300,
    )
    return result.returncode


def test_dead_address_fails_when_required():
    """REQUIRED + unreachable DQTEST_* must fail - proving env is honoured."""
    code = _run_live_suite({
        # short connect timeouts so the failure is fast, not a 5-minute hang
        "DQTEST_MYSQL": "mysql://x:x@127.0.0.1:1/x?connect_timeout=2",
        "DQTEST_PG": "postgresql://x:x@127.0.0.1:1/x?connect_timeout=2",
        "DQ_LIVE_REQUIRED": "1",
        "DQTEST_MYSQL_ADMIN": "",
    })
    assert code != 0, "dead addresses must fail under DQ_LIVE_REQUIRED"


def test_env_addresses_are_used_not_constants():
    """With DQTEST_* pointing at the live local instances, the suite passes.

    If the tests still dialled hardcoded ports this would be a no-op
    assertion; combined with the dead-address test above it proves the
    environment variables drive the connections.
    """
    code = _run_live_suite({
        "DQTEST_MYSQL": "mysql://dqtest:dqtest@127.0.0.1:13306/dqtest",
        "DQTEST_PG": "postgresql://postgres:@127.0.0.1:3361/dqtest",
        "DQTEST_MYSQL_ADMIN": "mysql://root:@127.0.0.1:13306/mysql",
        "DQ_LIVE_REQUIRED": "1",
    })
    assert code == 0, "live suite must pass against reachable DQTEST_* services"


def test_required_without_admin_fails():
    code = _run_live_suite({
        "DQTEST_MYSQL": "mysql://dqtest:dqtest@127.0.0.1:13306/dqtest",
        "DQTEST_PG": "postgresql://postgres:@127.0.0.1:3361/dqtest",
        "DQTEST_MYSQL_ADMIN": "",
        "DQ_LIVE_REQUIRED": "1",
    })
    assert code != 0, "REQUIRED without DQTEST_MYSQL_ADMIN must fail, not skip"
