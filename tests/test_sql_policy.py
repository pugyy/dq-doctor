"""SQL rule shape policy tests (audit P1-9).

The policy is a pure function over statement text; these tests pin the
accepted and rejected shapes without touching a database.
"""
from __future__ import annotations

import pytest

from dqdoctor.sqlpolicy import expect_problem, read_only_problem, statement_words

REJECTED = [
    "WITH d AS (DELETE FROM t RETURNING *) SELECT COUNT(*) FROM d",
    "WITH x AS (UPDATE t SET v = 1 RETURNING *) SELECT COUNT(*) FROM x",
    "SELECT * FROM read_text('/etc/passwd')",
    "SELECT * FROM read_csv_auto('/tmp/x.csv')",
    "SELECT * FROM read_parquet('/tmp/x.parquet')",
    "SELECT 1; DROP TABLE t",
    "UPDATE t SET x = 1",
    "INSERT INTO t VALUES (1)",
    "CREATE TABLE x (a INTEGER)",
    "ATTACH 'other.db' AS other",
    "COPY t TO '/tmp/out.csv'",
]

ACCEPTED = [
    "SELECT COUNT(*) FROM t",
    "SELECT COUNT(*) FROM t WHERE v < 0",
    "SELECT ';' AS semi FROM t",
    "SELECT 'a -- not a comment' FROM t",
    "/* leading comment */ SELECT COUNT(*) FROM t",
    "SELECT COUNT(*) FROM t -- trailing comment",
    "WITH x AS (SELECT 1 AS n) SELECT COUNT(*) FROM x",
    "SELECT \"order\" FROM \"select\"",
    "SELECT COUNT(*) FROM t;",
    # function arguments must not look like table sources (a comma branch in
    # _REPLACEMENT_SCAN rejected all three of these)
    "SELECT count(*) FROM t WHERE status IN ('ok','bad')",
    "SELECT COALESCE(a, 'x') FROM t",
    "SELECT replace(name,'a','b') FROM t",
    "SELECT concat_ws(',', a, 'b') FROM t",
    "SELECT substr(name, 1, 'x' IS NOT NULL) FROM t",
]


@pytest.mark.parametrize("statement", REJECTED)
def test_policy_rejects(statement):
    problem = read_only_problem(statement)
    assert problem is not None, "should have been rejected"


@pytest.mark.parametrize("statement", ACCEPTED)
def test_policy_accepts(statement):
    assert read_only_problem(statement) is None


def test_policy_ignores_keywords_inside_strings():
    """A quoted 'delete' is data, not a statement keyword."""
    assert read_only_problem("SELECT 'delete' AS word FROM t") is None


def test_expect_problem_requires_bounds():
    assert expect_problem({"mode": "eq", "value": 0}) is None
    assert expect_problem({"mode": "between", "min": 1, "max": 2}) is None
    assert expect_problem({"mode": "wat", "value": 0}) is not None
    assert expect_problem({}) is not None
    assert expect_problem("nope") is not None


def test_statement_words_strips_literals_and_comments():
    words = statement_words("SELECT 'DELETE' FROM t -- UPDATE")
    assert "delete" not in words
    assert "update" not in words
    assert "select" in words
