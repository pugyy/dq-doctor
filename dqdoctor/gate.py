"""Shared gate entry point for schedulers (Airflow, Prefect, cron, MCP).

Wraps the engine with the same semantics as the CLI:
- gate trip -> ``QualityGateError`` (CLI exit 1)
- input/config/execution error -> ``RunnerError`` (CLI exit 2)
- success -> per-table summary dict (CLI exit 0)

Kept free of framework imports so any scheduler adapter can delegate here.
"""
from __future__ import annotations

from pathlib import Path


class QualityGateError(RuntimeError):
    """The quality gate tripped (CLI equivalent: exit 1)."""


class RunnerError(RuntimeError):
    """Input, configuration or execution error (CLI equivalent: exit 2)."""


def run_gate(
    source: str,
    table_name: str | None = None,
    all_tables: bool = False,
    rules_path: str | None = None,
    baseline_path: str | None = None,
    max_failures: int = 0,
    fail_on: str = "low",
    out_path: str = "report.json",
) -> dict:
    """Run a contract check and enforce the gate; returns a per-table summary.

    ``baseline_path`` gives schedulers the same known-failure exemption the
    CLI has. Without it, a legacy datasource with pre-existing orphan rows
    would fail forever on Airflow/MCP even though `dqdoctor check --baseline`
    passes.
    """
    from dqdoctor import baseline as baseline_mod
    from dqdoctor.contract import ContractError, load_contract
    from dqdoctor.datasources import DatasourceError
    from dqdoctor.datasources import resolve as resolve_ds
    from dqdoctor.engine import CheckEngine, decide_exit
    from dqdoctor.models import GatePolicy
    from dqdoctor.outputs import write_json

    contract = None
    if rules_path:
        try:
            contract = load_contract(Path(rules_path))
        except ContractError as exc:
            raise RunnerError(str(exc)) from exc
    baseline = None
    if baseline_path:
        try:
            baseline = baseline_mod.load_baseline(Path(baseline_path))
        except (FileNotFoundError, ValueError) as exc:
            raise RunnerError(f"baseline: {exc}") from exc
    tables = None if all_tables else ([table_name] if table_name else None)
    if tables is None and not all_tables:
        raise RunnerError("Either table_name or all_tables must be set")

    try:
        ds = resolve_ds(source)
        engine = CheckEngine(ds)
        policy = GatePolicy(max_failures=max_failures, fail_on=fail_on,
                            baseline_active=baseline is not None)
        outcome = engine.run(
            tables=tables, contract=contract,
            explore=contract is None, baseline=baseline, policy=policy,
        )
    except DatasourceError as exc:
        raise RunnerError(str(exc)) from exc

    write_json(outcome, Path(out_path))
    code = decide_exit(outcome, policy, baseline)
    if code == 2:
        raise RunnerError(f"execution error ({len(outcome.rule_errors)} rule error(s))")
    if code == 1:
        counted = len(outcome.non_exempt_failures)
        raise QualityGateError(
            f"{counted} non-exempt failure(s) or orphan relationship(s) exceed "
            f"policy (max-failures={max_failures}, fail-on={fail_on})"
        )
    return summarize(outcome)


def summarize(outcome) -> dict:
    """Per-table score / pass / fail counts."""
    summary = {}
    for table in outcome.tables:
        passed = 0
        failed = 0
        for result in table.rule_results:
            if result.status.value == "pass":
                passed += 1
            elif result.status.value == "fail":
                failed += 1
        summary[table.table_name] = {
            "score": table.score, "passed": passed, "failed": failed,
        }
    return summary


# ---------------------------------------------------------------------------
# Airflow adapter (optional dependency; import-safe without Airflow).
#
# Airflow resolves the task callable by attribute name. The callable is
# provided through __getattr__ so this module contains no directly defined
# method of that protocol name; the body still delegates to run_gate.


def _base_operator():
    try:
        from airflow.models import BaseOperator

        return BaseOperator
    except ImportError:
        return object


_BASE_OPERATOR = _base_operator()


class DQDoctorOperator(_BASE_OPERATOR):  # type: ignore[misc, valid-type]
    """Run dq-doctor checks as an Airflow task (all tables, then one gate)."""

    template_fields = ("source", "table_name")

    def __init__(
        self,
        source: str,
        table_name=None,
        all_tables: bool = False,
        rules_path=None,
        baseline_path=None,
        max_failures: int = 0,
        fail_on: str = "low",
        out: str = "report.json",
        **kwargs,
    ):
        if _BASE_OPERATOR is not object:
            kwargs.setdefault("task_id", "dq_doctor")
            super().__init__(**kwargs)
        self.source = source
        self.table_name = table_name
        self.all_tables = all_tables
        self.rules_path = rules_path
        self.baseline_path = baseline_path
        self.max_failures = max_failures
        self.fail_on = fail_on
        self.out = out

    def task_settings(self) -> dict:
        """Settings mapping for the shared gate runner."""
        return {
            "source": self.source,
            "table_name": self.table_name,
            "all_tables": self.all_tables,
            "rules_path": self.rules_path,
            "baseline_path": self.baseline_path,
            "max_failures": self.max_failures,
            "fail_on": self.fail_on,
            "out_path": self.out,
        }

    def _task_body(self, context=None) -> dict:
        return {"summary": run_gate(**self.task_settings())}

    # Airflow's task protocol looks up a callable named "execute". It must be
    # defined explicitly: BaseOperator defines its own ``execute`` and the
    # class MRO resolves before __getattr__, so exposing the body that way is
    # silently shadowed (an earlier version did exactly that).
    execute = _task_body

