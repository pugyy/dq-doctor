"""Execution primitive for operator-authored SQL rules.

One job: run a statement the *operator* wrote in their own contract, with
a read-only session, a timeout and a one-value contract. Callers validate
the statement first via ``dqdoctor.sqlpolicy.read_only_problem``.

The statement is the product's input (like a dbt test body): dq-doctor
never assembles it and never interpolates a value into it. Guardrails:
read-only sessions, single-statement SELECT/WITH, statement timeout, and
an exactly-one-row/one-column result contract.
"""
from __future__ import annotations

import threading
from typing import Any


def run_operator_query(con, statement: str, timeout: float) -> Any:
    """Run one validated operator statement; return its single scalar."""
    if con.backend == "duckdb":
        return _duckdb_scalar(con, statement, timeout)
    con.set_statement_timeout(timeout)
    # SQLAlchemy native driver passthrough (no ORM text() templating).
    row = con._raw.exec_driver_sql(statement).fetchone()
    return _one_scalar(row)


def _duckdb_scalar(con, statement: str, timeout: float) -> Any:
    """DuckDB has no statement timeout; run off-thread and interrupt."""
    outcome: dict[str, Any] = {}
    done = threading.Event()
    cursor = con._raw.cursor()

    def _worker() -> None:
        try:
            rows = cursor.sql(statement).limit(1).fetchall()
            outcome["row"] = rows[0] if rows else None
        except Exception as exc:  # noqa: BLE001 - transported to caller
            outcome["error"] = exc
        finally:
            done.set()

    worker = threading.Thread(target=_worker, daemon=True)
    worker.start()
    if not done.wait(timeout):
        con.interrupt()
        raise TimeoutError(f"query exceeded {timeout:.0f}s timeout")
    if "error" in outcome:
        raise outcome["error"]
    return _one_scalar(outcome["row"])


def _one_scalar(row) -> Any:
    if row is None:
        raise ValueError("query returned no rows; a scalar result is required")
    if len(row) != 1:
        raise ValueError(
            f"query returned {len(row)} columns; exactly one scalar column is required"
        )
    return row[0]
