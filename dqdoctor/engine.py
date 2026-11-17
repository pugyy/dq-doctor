"""The check engine: one callable that turns a datasource + contract into a
``CheckOutcome``, reused by the CLI, Airflow operator, exporters and MCP.

Responsibilities (one run, one connection):

1. open the datasource once and reuse the connection for everything;
2. build the FK plan once and check every relationship exactly once;
3. per table: profile (batched aggregates) -> rules (contract) or
   suggestions (explore) -> execute -> score;
4. apply a baseline (known failures exempted, deterioration still gates);
5. decide the exit code centrally: 2 on any execution error, 1 when the
   quality gate trips, 0 otherwise.

Partially failed runs still return the results collected so far; the exit
code keeps reporting the execution error.
"""
from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from dqdoctor import baseline as baseline_mod
from dqdoctor import fkcheck, rulecheck, scoring
from dqdoctor.contract import Contract
from dqdoctor.datasources import DataSource
from dqdoctor.models import (
    CheckOutcome,
    FKIssue,
    GatePolicy,
    PIIFinding,
    RuleResult,
    RuleSpec,
    RuleStatus,
    TableCheck,
    TableProfile,
    severity_at_least,
)
from dqdoctor.profiling import profile_table
from dqdoctor.suggest import suggest_for_table


def utc_now() -> datetime:
    return datetime.now(UTC)


class CheckEngine:
    def __init__(
        self,
        datasource: DataSource,
        clock: Callable[[], datetime] | None = None,
        sql_timeout: float = 30.0,
        include_heuristic_fk: bool = True,
    ):
        self.datasource = datasource
        self.clock = clock or utc_now
        self.sql_timeout = sql_timeout
        self.include_heuristic_fk = include_heuristic_fk

    def run(
        self,
        tables: list[str] | None = None,
        contract: Contract | None = None,
        baseline: baseline_mod.Baseline | None = None,
        explore: bool = False,
        sample_rows: int | None = None,
        policy: GatePolicy | None = None,
    ) -> CheckOutcome:
        started = datetime.now(UTC)
        con = self.datasource.open(read_only=True)
        try:
            if con.backend != "duckdb":
                con.enforce_read_only()
            table_list = tables if tables else self.datasource.tables()
            fk_plan = fkcheck.build_plan(con, self.include_heuristic_fk)
            fk_issues: list[FKIssue] = []
            try:
                fk_issues = fkcheck.check_all(con, fk_plan)
            except Exception as exc:  # noqa: BLE001 - surfaced, run continues
                fk_issues = [
                    FKIssue(
                        from_table="*", from_column="*", to_table="*", to_column="*",
                        orphan_rows=0, total_rows=0, error=f"FK check failed: {exc}",
                    )
                ]

            table_checks: list[TableCheck] = []
            for table in table_list:
                table_checks.append(
                    self._check_table(con, table, contract, explore, sample_rows,
                                      fk_issues)
                )
        finally:
            con.close()

        outcome = CheckOutcome(
            dqdoctor_version=_version(),
            started_at=started.isoformat(),
            finished_at=datetime.now(UTC).isoformat(),
            datasource=self.datasource.describe(),
            tables=table_checks,
            fk_issues=fk_issues,
            gate_policy=policy,
        )
        if baseline is not None:
            baseline_mod.apply_baseline(outcome, baseline)
        return outcome

    # -----------------------------------------------------------------------

    def _check_table(
        self,
        con,
        table: str,
        contract: Contract | None,
        explore: bool,
        sample_rows: int | None,
        fk_issues: list[FKIssue],
    ) -> TableCheck:
        try:
            profile = profile_table(con, self.datasource.describe(), table,
                                    sample_rows=sample_rows)
        except Exception as exc:  # noqa: BLE001 - partial-failure contract
            return TableCheck(
                table_name=table,
                profile=TableProfile(
                    datasource=self.datasource.describe(), table_name=table,
                    row_count=0, columns=[],
                ),
                rule_results=[
                    RuleResult(
                        rule_id="engine:table", rule_type="engine", column="*",
                        status=RuleStatus.ERROR,
                        message=f"profiling failed: {type(exc).__name__}: {exc}",
                    )
                ],
            )

        if contract is not None and not explore:
            specs = contract.specs_for(table)
            results = rulecheck.execute_rules(
                con, table, profile, specs, self.clock, self.sql_timeout
            )
            results.extend(self._sql_rules(con, specs))
        else:
            specs = suggest_for_table(profile)
            results = [
                RuleResult(
                    rule_id=s.id, rule_type=s.type, column=s.column,
                    status=RuleStatus.SUGGESTION, severity=s.severity,
                    message=s.reason or "learned from this batch (suggestion)",
                    source="suggested",
                )
                for s in specs
            ]

        pii = []
        evidence_map = getattr(profile, "pii_evidence", {}) or {}
        for c in profile.columns:
            if not c.pii_type:
                continue
            ev = evidence_map.get(c.name)
            pii.append(
                PIIFinding(
                    column=c.name,
                    pii_type=c.pii_type,
                    matched_fraction=(
                        getattr(ev, "matched_fraction", 0.0) if ev else 0.0
                    ),
                    sample_size=getattr(ev, "sample_size", 0) if ev else 0,
                )
            )
        related = [
            fk for fk in fk_issues
            if fk.from_table == table or fk.to_table == table
        ]
        check = TableCheck(
            table_name=table, profile=profile, rule_results=results,
            pii_findings=pii, fk_issues=related,
        )
        score, breakdown = scoring.score_table(check)
        check.score = score
        check.score_breakdown = breakdown
        return check

    def _sql_rules(self, con, specs: list[RuleSpec]) -> list[RuleResult]:
        """Execute opt-in SQL rules through the guarded primitive."""
        from dqdoctor.sqlrules import check_sql

        return [
            check_sql(con, s, self.sql_timeout)
            for s in specs
            if s.type == "sql" and s.enabled
        ]


# ---------------------------------------------------------------------------
# Exit-code decision (single place)


def decide_exit(
    outcome: CheckOutcome,
    policy: GatePolicy | None,
    baseline: baseline_mod.Baseline | None = None,
) -> int:
    """0 = success/within policy, 1 = quality gate tripped, 2 = errors.

    Gate semantics (documented in README):
    - ``--fail-on`` selects which failures participate at all; failures
      below the threshold are reported but do not gate.
    - ``--max-failures`` tolerates up to N *participating* failures.
    So a run trips when (count of participating failures) > max_failures.
    """
    if outcome.rule_errors:
        return 2
    for fk in outcome.fk_issues:
        if fk.error:
            return 2
    if policy is None:
        return 0
    participating = [
        r for r in outcome.non_exempt_failures
        if severity_at_least(r.severity, policy.fail_on)
    ]
    if len(participating) > policy.max_failures:
        return 1
    if baseline is not None:
        fk_new = [
            fk for fk in outcome.fk_issues
            if fk.orphan_rows > 0 and not baseline_mod.fk_is_exempt(fk, baseline)
        ]
        if fk_new:
            return 1
    return 0


def _version() -> str:
    from dqdoctor import __version__

    return __version__
