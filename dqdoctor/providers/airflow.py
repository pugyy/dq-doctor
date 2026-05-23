from __future__ import annotations

from pathlib import Path
from typing import Any, Optional


def _get_base_operator():
    try:
        from airflow.models import BaseOperator

        return BaseOperator
    except ImportError:
        return object


class DQDoctorOperator(_get_base_operator()):
    template_fields = ("db_path", "table_name")

    def __init__(
        self,
        db_path: str,
        table_name: Optional[str] = None,
        all_tables: bool = False,
        max_failures: int = 0,
        out: str = "report.html",
        **kwargs: Any,
    ):
        base = _get_base_operator()
        if base is not object:
            kwargs.setdefault("task_id", "dq_doctor")
            super().__init__(**kwargs)
        self.db_path = db_path
        self.table_name = table_name
        self.all_tables = all_tables
        self.max_failures = max_failures
        self.out = out

    def execute(self, context: Any = None) -> dict:
        from dqdoctor.connectors.auto import get_connection, list_tables
        from dqdoctor.profiler import profile_table
        from dqdoctor.reporter import build_report, save_html
        from dqdoctor.rule_engine import generate_rules
        from dqdoctor.validator import validate_rules

        if self.all_tables:
            con = get_connection(self.db_path, read_only=True)
            try:
                tables = list_tables(con)
            finally:
                con.close()
        elif self.table_name:
            tables = [self.table_name]
        else:
            raise ValueError("Either table_name or all_tables must be set")

        results_summary = {}
        for table in tables:
            profile = profile_table(self.db_path, table)
            rules = generate_rules(profile)
            results = validate_rules(self.db_path, table, rules)
            report = build_report(profile, rules, results)

            out_path = self.out
            if len(tables) > 1:
                p = Path(self.out)
                out_path = str(p.with_name(f"{p.stem}_{table}{p.suffix}"))
            save_html(report, out_path)

            results_summary[table] = {
                "total": report.total_rules,
                "passed": report.passed_rules,
                "failed": report.failed_rules,
            }

            if report.failed_rules > self.max_failures:
                raise RuntimeError(
                    f"Table '{table}' has {report.failed_rules} failures "
                    f"(max allowed: {self.max_failures})"
                )

        return results_summary
