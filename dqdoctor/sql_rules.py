from __future__ import annotations

from typing import Any

from dqdoctor.connectors.auto import get_connection
from dqdoctor.models import ValidationResult


def execute_sql_rules(
    db_path: str, table_name: str, sql_rules: list[dict[str, Any]],
) -> list[ValidationResult]:
    if not sql_rules:
        return []

    con = get_connection(str(db_path))
    try:
        results: list[ValidationResult] = []
        for rule in sql_rules:
            name = rule.get("name", "unnamed_sql")
            query = rule.get("query", "")
            expect = rule.get("expect", 0)

            if not query:
                results.append(ValidationResult(
                    rule_id=f"sql.{name}",
                    rule_type="sql",
                    column="*",
                    passed=True,
                    failed_count=0,
                    total_count=0,
                    message=f"SQL rule '{name}' has no query, skipped.",
                ))
                continue

            try:
                row = con.fetchone(query)
                actual = row[0] if row else 0
                passed = actual == expect
                results.append(ValidationResult(
                    rule_id=f"sql.{name}",
                    rule_type="sql",
                    column="*",
                    passed=passed,
                    failed_count=actual if not passed else 0,
                    total_count=actual,
                    message=(
                        f"SQL rule '{name}': got {actual}, expected {expect}."
                        if not passed
                        else f"SQL rule '{name}': passed ({actual} == {expect})."
                    ),
                ))
            except Exception as e:
                results.append(ValidationResult(
                    rule_id=f"sql.{name}",
                    rule_type="sql",
                    column="*",
                    passed=False,
                    failed_count=1,
                    total_count=1,
                    message=f"SQL rule '{name}' error: {e}",
                ))
        return results
    finally:
        con.close()
