"""dq-doctor CLI: parameter handling and rendering only.

All execution lives in ``dqdoctor.engine.CheckEngine``. Exit codes:
0 = success or within gate policy, 1 = quality gate tripped,
2 = input/configuration/execution error.
"""
from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from dqdoctor import __version__
from dqdoctor import baseline as baseline_mod
from dqdoctor import contract as contract_mod
from dqdoctor.baseline import fk_is_exempt
from dqdoctor.contract import ContractError
from dqdoctor.datasources import (
    DataSource,
    DatasourceError,
)
from dqdoctor.datasources import (
    resolve as resolve_datasource,
)
from dqdoctor.engine import CheckEngine, decide_exit, participating_failures
from dqdoctor.models import CheckOutcome, GatePolicy, RuleStatus
from dqdoctor.outputs import write_html, write_json, write_junit

app = typer.Typer(
    name="dqdoctor",
    help="Profile tables, pin a data quality contract, gate new batches.",
    add_completion=False,
    no_args_is_help=True,
)
console = Console()

EXIT_OK, EXIT_GATE, EXIT_ERROR = 0, 1, 2


def _version_callback(value: bool) -> None:
    if value:
        console.print(f"dq-doctor {__version__}")
        raise typer.Exit(EXIT_OK)


@app.callback()
def main(
    version: bool = typer.Option(
        False, "--version", callback=_version_callback, is_eager=True,
        help="Show version and exit",
    ),
) -> None:
    """dq-doctor: one command to profile, contract and gate data quality."""


def _fail(msg: str, code: int = EXIT_ERROR) -> None:
    console.print(f"[red]Error:[/red] {msg}")
    raise typer.Exit(code)


def _safe_stem(name: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9_.-]", "_", name).strip("._") or "table"
    return stem[:80]


def _multi_out(out: Path, table: str) -> Path:
    """Stable, collision-free per-table output path."""
    return out.with_name(f"{out.stem}_{_safe_stem(table)}{out.suffix}")


def _resolve_ds(db: str | None, config: Path | None) -> DataSource:
    if db is None and config is None and not Path(".dqdoctor.yml").exists():
        _fail("--db is required (or register datasources in .dqdoctor.yml via `dqdoctor init`).")
    try:
        return resolve_datasource(db or "", config_path=config)
    except DatasourceError as exc:
        _fail(str(exc))


def _atomic_write(path: Path, writer) -> Path:
    """Write to a temp sibling, fsync, then replace (for --force flows)."""
    tmp = path.with_name(path.name + ".tmp")
    writer(tmp)
    tmp.replace(path)
    return path


# ---------------------------------------------------------------------------
# demo / init


@app.command()
def demo(
    output: str | None = typer.Option(None, "--output", "-o", help="Output DuckDB path"),
    dirty: bool = typer.Option(False, "--dirty", help="Demo data with intentional issues"),
    force: bool = typer.Option(False, "--force", help="Overwrite an existing file"),
) -> None:
    """Create a demo DuckDB database (refuses to overwrite without --force)."""
    from dqdoctor.demo import create_demo_db, create_dirty_db

    db_path = Path(output) if output else Path("dirty.duckdb" if dirty else "demo.duckdb")
    if db_path.exists() and not force:
        _fail(
            f"{db_path} already exists. Pass --force to overwrite "
            "(the file is fully rebuilt in a temp sibling before replacing)."
        )
    creator = create_dirty_db if dirty else create_demo_db
    creator(str(db_path))
    console.print(f"[green]Demo database created:[/green] {db_path}")
    console.print(f"[dim]Next: dqdoctor check --db {db_path} --all-tables[/dim]")


@app.command()
def doctor() -> None:
    """Check installation health: core deps, optional extras, package data."""
    import importlib
    import sys

    console.print(Panel(f"[bold]dq-doctor[/bold]  v{__version__}", border_style="blue",
                        expand=False))
    checks: list[tuple[str, bool, str, bool]] = []  # name, ok, detail, optional

    py = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    py_ok = sys.version_info >= (3, 12)
    checks.append(("Python version", py_ok,
                   py + (" OK" if py_ok else " FAIL: 1.0 needs 3.12+"), False))
    checks.append(("dq-doctor version", True, __version__, False))

    try:
        import duckdb

        checks.append(("DuckDB", True, duckdb.__version__, False))
    except ImportError:
        checks.append(("DuckDB", False, "not installed", False))

    template = Path(__file__).parent / "templates" / "report.html"
    checks.append(("Report template", template.exists(),
                   "OK" if template.exists() else "MISSING", False))
    for name, extra in (("sqlalchemy", "sql"), ("psycopg2", "sql"),
                        ("pymysql", "sql"), ("openai", "llm"),
                        ("flask", "dashboard"), ("mcp", "mcp")):
        try:
            mod = importlib.import_module(name)
            checks.append((name, True, getattr(mod, "__version__", "installed"), True))
        except ImportError:
            checks.append((f"{name} [{extra}]", False, f"not installed "
                           f"(pip install 'dq-doctor[{extra}]')", True))

    table = Table()
    table.add_column("Check", style="bold")
    table.add_column("Status")
    table.add_column("Detail")
    core_ok = True
    for name, ok, detail, optional in checks:
        icon = ("[green]OK[/green]" if ok
                else "[yellow]--[/yellow]" if optional
                else "[red]MISS[/red]")
        if not ok and not optional:
            core_ok = False
        table.add_row(name, icon, detail)
    console.print(table)
    console.print("[green]All core checks passed.[/green]" if core_ok
                  else "[red]Some core checks failed.[/red]")


@app.command()
def init(
    force: bool = typer.Option(False, "--force", help="Overwrite existing config"),
) -> None:
    """Create a .dqdoctor.yml with datasource aliases."""
    path = Path(".dqdoctor.yml")
    if path.exists() and not force:
        _fail(f"{path} already exists; pass --force to overwrite.")
    content = (
        "# dq-doctor 1.0 configuration: named datasources\n"
        "datasources:\n"
        "  demo: demo.duckdb\n"
        "  # prod: postgresql://user:pass@host:5432/db?schema=analytics\n"
        "default: demo\n"
    )
    _atomic_write(path, lambda p: p.write_text(content, encoding="utf-8"))
    console.print("[green]Created .dqdoctor.yml[/green] with a 'demo' datasource alias.")


# ---------------------------------------------------------------------------
# tables / profile


@app.command()
def tables(
    db: str | None = typer.Option(None, "--db", help="Datasource spec or alias"),
    config: Path | None = typer.Option(None, "--config", help="Config file path"),
) -> None:
    """List tables in a datasource."""
    ds = _resolve_ds(db, config)
    try:
        names = ds.tables()
    except DatasourceError as exc:
        _fail(str(exc))
    t = Table(show_header=True, header_style="bold")
    t.add_column("#", style="dim", width=4)
    t.add_column("Table", style="bold")
    t.add_column("Columns", justify="right")
    con = ds.open()
    try:
        from dqdoctor.queries import table_columns

        for i, name in enumerate(names, 1):
            t.add_row(str(i), name, str(len(table_columns(con, name))))
    finally:
        con.close()
    console.print(t)


@app.command()
def profile(
    db: str | None = typer.Option(None, "--db", help="Datasource spec or alias"),
    table: str = typer.Option(..., "--table", help="Table name"),
    sample_rows: int | None = typer.Option(
        None, "--sample-rows", help="Deterministic first-N sampling for profiling"
    ),
    out: Path | None = typer.Option(None, "--out", help="Save profile JSON (redacted)"),
) -> None:
    """Profile one table (batched aggregates + PII evidence)."""
    ds = _resolve_ds(db, None)
    con = ds.open()
    try:
        from dqdoctor.profiling import profile_table

        result = profile_table(con, ds.describe(), table, sample_rows=sample_rows)
    except Exception as exc:  # noqa: BLE001
        _fail(f"profiling failed: {exc}")
    finally:
        con.close()
    t = Table(title=f"Profile: {table}")
    for header in ("Column", "Type", "Null%", "Distinct", "Semantic", "PII"):
        t.add_column(header)
    for col in result.columns:
        t.add_row(
            col.name, col.dtype, f"{col.null_rate:.1%}", str(col.distinct_count),
            col.inferred_semantic_type, col.pii_type or "-",
        )
    console.print(t)
    if result.sampling.method == "sample":
        console.print(
            f"[yellow]sampled[/yellow]: {result.sampling.sample_size}/"
            f"{result.sampling.row_count} rows (deterministic first-N slice)"
        )
    if out:
        payload = json_safe_profile(result)
        out.write_text(payload, encoding="utf-8")
        console.print(f"[green]Profile saved:[/green] {out} (redacted)")


def json_safe_profile(result) -> str:
    import json

    from dqdoctor.redact import redact_scalar

    data = json.loads(result.model_dump_json())
    for col in data["columns"]:
        col["min_value"] = redact_scalar(col.get("min_value"))
        col["max_value"] = redact_scalar(col.get("max_value"))
    return json.dumps(data, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# check / rules-init


@app.command()
def check(
    db: str | None = typer.Option(None, "--db", help="Datasource spec or alias"),
    table: str | None = typer.Option(None, "--table", help="Table to check"),
    all_tables: bool = typer.Option(False, "--all-tables", help="Check every table"),
    rules: Path | None = typer.Option(
        None, "--rules", help="1.0 contract file (pinned rules; no re-learning)"
    ),
    out: Path = typer.Option(Path("report.html"), "--out", help="HTML report path"),
    json_out: Path | None = typer.Option(None, "--json", help="JSON report path"),
    junit_out: Path | None = typer.Option(None, "--junit", help="JUnit XML path"),
    ci: bool = typer.Option(False, "--ci", help="Apply gate and exit codes"),
    max_failures: int = typer.Option(0, "--max-failures", help="Gate: allowed failures"),
    fail_on: str = typer.Option(
        "low", "--fail-on", help="Gate: trip on failures at this severity or higher"
    ),
    baseline: Path | None = typer.Option(None, "--baseline", help="Known-failure baseline"),
    sample_rows: int | None = typer.Option(None, "--sample-rows", help="Profiling sampling"),
    sql_timeout: float = typer.Option(30.0, "--sql-timeout", help="SQL rule timeout (s)"),
    config: Path | None = typer.Option(None, "--config", help="Config file path"),
) -> None:
    """Run a check.

    Without --rules this is explore mode: learned bounds appear as
    SUGGESTIONs, never as verified passes. With --rules the contract is
    executed as pinned; CI exit codes: 0 ok, 1 gate, 2 error.
    """
    if fail_on not in ("high", "medium", "low"):
        _fail(f"--fail-on must be high/medium/low, got {fail_on!r}")
    ds = _resolve_ds(db, config)
    contract = None
    if rules is not None:
        try:
            contract = contract_mod.load_contract(rules)
        except ContractError as exc:
            _fail(str(exc))
        if contract.datasource and db is None:
            ds = _resolve_ds(contract.datasource, config)
    base = None
    if baseline is not None:
        try:
            base = baseline_mod.load_baseline(baseline)
        except (FileNotFoundError, ValueError) as exc:
            _fail(f"baseline: {exc}")
        if base is not None and not isinstance(base, baseline_mod.Baseline):
            _fail(f"baseline: unexpected content in {baseline}")

    tables_wanted = None
    if all_tables:
        try:
            tables_wanted = ds.tables()
        except DatasourceError as exc:
            _fail(str(exc))
        if not tables_wanted:
            console.print("[yellow]No tables found.[/yellow]")
            raise typer.Exit(EXIT_OK)
    elif not table:
        _fail("--table is required (or use --all-tables).")

    policy = GatePolicy(max_failures=max_failures, fail_on=fail_on,
                        baseline_active=base is not None) if ci else None
    engine = CheckEngine(ds, sql_timeout=sql_timeout)
    try:
        outcome = engine.run(
            tables=tables_wanted or ([table] if table else None),
            contract=contract, baseline=base,
            explore=contract is None,
            sample_rows=sample_rows, policy=policy,
        )
    except DatasourceError as exc:
        _fail(str(exc))

    _render_outcome(outcome, contract_mode=contract is not None)
    paths = [_multi_or_single(out, outcome, write_html, ".html")]
    if json_out:
        paths.append(_multi_or_single(json_out, outcome, write_json, ".json"))
    if junit_out:
        write_junit(outcome, junit_out)
        paths.append(junit_out)
    console.print("[dim]Reports: " + ", ".join(str(p) for p in paths) + "[/dim]")

    # Execution errors always exit 2, with or without --ci: a run that could
    # not execute must never look successful to a caller. --ci additionally
    # turns quality-gate failures (FK orphans + rule failures) into exit 1.
    errors = decide_exit(outcome, None)
    if errors == EXIT_ERROR:
        raise typer.Exit(EXIT_ERROR)
    if ci:
        code = decide_exit(outcome, policy, base)
        if code == EXIT_GATE:
            counted = participating_failures(outcome, policy)
            orphan_pairs = [
                fk for fk in outcome.fk_issues
                if fk.orphan_rows > 0
                and not (base is not None and fk_is_exempt(fk, base))
            ]
            orphan_note = (
                f", plus {len(orphan_pairs)} orphan relationship(s)"
                if orphan_pairs else ""
            )
            console.print(
                f"[red]CI gate tripped:[/red] {len(counted)} non-exempt failure(s) "
                f"at or above '{fail_on}' (max-failures={max_failures})"
                f"{orphan_note}."
            )
        raise typer.Exit(code)
    if outcome.rule_errors:
        console.print(
            f"[magenta]{len(outcome.rule_errors)} rule error(s)[/magenta] - "
            "re-run with --ci to fail the pipeline on them."
        )


def _multi_or_single(out: Path, outcome: CheckOutcome, writer, suffix: str) -> Path:
    if len(outcome.tables) == 1:
        return writer(outcome, out)
    written = None
    for table in outcome.tables:
        sub = CheckOutcome(
            dqdoctor_version=outcome.dqdoctor_version,
            started_at=outcome.started_at, finished_at=outcome.finished_at,
            datasource=outcome.datasource, tables=[table],
            fk_issues=outcome.fk_issues, gate_policy=outcome.gate_policy,
        )
        written = writer(sub, _multi_out(out, table.table_name))
    return written or out


def _render_outcome(outcome: CheckOutcome, contract_mode: bool) -> None:
    mode = "contract" if contract_mode else "explore (suggestions, nothing verified)"
    console.print(Panel(f"mode: {mode}  datasource: {outcome.datasource}"))
    for table in outcome.tables:
        score = "n/a" if table.score is None else f"{table.score}/100"
        counts = {s: 0 for s in RuleStatus}
        for r in table.rule_results:
            counts[r.status] += 1
        console.print(
            f"  [bold]{table.table_name}[/bold]  score {score}  "
            f"[green]pass {counts[RuleStatus.PASS]}[/green]  "
            f"[red]fail {counts[RuleStatus.FAIL]}[/red]  "
            f"[yellow]skip {counts[RuleStatus.SKIP]}[/yellow]  "
            f"[cyan]suggest {counts[RuleStatus.SUGGESTION]}[/cyan]  "
            f"[magenta]error {counts[RuleStatus.ERROR]}[/magenta]"
        )
        for r in table.rule_results:
            style = {
                RuleStatus.PASS: "green", RuleStatus.FAIL: "red",
                RuleStatus.SKIP: "yellow", RuleStatus.SUGGESTION: "cyan",
                RuleStatus.ERROR: "magenta",
            }[r.status]
            exempt = " [dim](baseline-exempted)[/dim]" if r.exempted else ""
            console.print(f"    [{style}]{r.status.value.upper()}[/{style}] "
                          f"{r.rule_id}: {r.message}{exempt}")
        for p in table.pii_findings:
            console.print(f"    [yellow]PII[/yellow] {p.column}: {p.pii_type} "
                          f"({p.sample_size} samples)")
    for fk in outcome.fk_issues:
        if fk.error:
            console.print(f"  [magenta]FK ERROR[/magenta] {fk.error}")
        elif fk.orphan_rows:
            console.print(
                f"  [red]ORPHAN[/red] {fk.from_table}.{fk.from_column} -> "
                f"{fk.to_table}.{fk.to_column}: {fk.orphan_rows}/{fk.total_rows} "
                f"({'declared' if fk.declared else 'heuristic'})"
            )


@app.command("rules-init")
def rules_init(
    db: str | None = typer.Option(None, "--db", help="Datasource spec or alias"),
    table: str | None = typer.Option(
        None, "--table", help="Table name (use --all-tables for every table)"
    ),
    all_tables: bool = typer.Option(False, "--all-tables", help="Contract for every table"),
    out: Path = typer.Option(Path("contract.yml"), "--out", help="Contract output path"),
) -> None:
    """Generate an editable 1.0 contract from current (reference) data."""
    if not table and not all_tables:
        _fail("--table or --all-tables is required.")
    ds = _resolve_ds(db, None)
    engine = CheckEngine(ds)
    names = ds.tables() if all_tables else [table]
    outcome = engine.run(tables=names, explore=True)
    specs = {}
    from dqdoctor.suggest import suggest_for_table, table_scoped

    for tc in outcome.tables:
        specs[tc.table_name] = [
            table_scoped(s, tc.table_name) for s in suggest_for_table(tc.profile)
        ]
    contract = contract_mod.build_contract(
        # Persist the ORIGINAL spec so `check --rules` can reconnect; the
        # redacted form is display-only and would literally be a "***"
        # password.
        [tc.profile for tc in outcome.tables], specs, datasource=ds.persistent_ref()
    )
    contract_mod.save_contract(contract, out)
    total = sum(len(v) for v in specs.values())
    console.print(f"[green]Contract written:[/green] {out} ({total} rules, "
                  f"{len(specs)} table(s))")
    console.print(f"[dim]Edit it, then: dqdoctor check --db {ds.describe()} "
                  f"--all-tables --rules {out} --ci[/dim]")
    console.print("[dim]The contract stores the full datasource reference; "
                  "--db is only needed to override it.[/dim]")


# ---------------------------------------------------------------------------
# baseline


@app.command()
def baseline(
    action: str = typer.Argument(..., help="capture | help"),
    db: str | None = typer.Option(None, "--db", help="Datasource spec or alias"),
    rules: Path | None = typer.Option(None, "--rules", help="Contract file"),
    all_tables: bool = typer.Option(True, "--all-tables", help="Capture across tables"),
    out: Path = typer.Option(Path("baseline.json"), "--out", help="Baseline output"),
) -> None:
    """Capture current failures as the known-failure baseline."""
    if action != "capture":
        _fail("usage: dqdoctor baseline capture --db ... --rules ...")
    ds = _resolve_ds(db, None)
    contract = None
    if rules is not None:
        try:
            contract = contract_mod.load_contract(rules)
        except ContractError as exc:
            _fail(str(exc))
    engine = CheckEngine(ds)
    outcome = engine.run(tables=None if all_tables else None, contract=contract,
                         explore=contract is None)
    base = baseline_mod.capture(outcome, datetime.now(UTC).isoformat())
    baseline_mod.save_baseline(base, out)
    console.print(f"[green]Baseline captured:[/green] {out} "
                  f"({len(base.entries)} known rule failures, "
                  f"{len(base.fk_pairs)} failing FK pairs)")


# ---------------------------------------------------------------------------
# migrate / export / drift / mcp / serve


@app.command()
def migrate(
    legacy: Path = typer.Option(..., "--in", help="Legacy 0.7 rules.yml or .dqdoctor.yml"),
    out: Path = typer.Option(Path("contract.yml"), "--out", help="1.0 contract output"),
) -> None:
    """One-time migration of a 0.7 rules file or config into a 1.0 contract."""
    try:
        contract = contract_mod.migrate_legacy(legacy)
    except ContractError as exc:
        _fail(str(exc))
    contract_mod.save_contract(contract, out)
    total = sum(len(tr.rules) for tr in contract.tables.values())
    console.print(f"[green]Migrated:[/green] {legacy} -> {out} ({total} rules)")


@app.command()
def export(
    rules: Path = typer.Option(..., "--rules", help="1.0 contract file"),
    fmt: str = typer.Option(..., "--format", help="dbt | gx | soda | deequ | markdown"),
    out: Path = typer.Option(..., "--out", help="Output file"),
) -> None:
    """Export a contract (preserving overrides/disables/params)."""
    from dqdoctor.exporters import dbt, deequ, gx, markdown, soda

    try:
        contract = contract_mod.load_contract(rules)
    except ContractError as exc:
        _fail(str(exc))
    exporters = {
        "dbt": dbt.save, "gx": gx.save, "soda": soda.save,
        "deequ": deequ.save, "markdown": markdown.save,
    }
    if fmt not in exporters:
        _fail(f"Unknown format {fmt!r}; choose from {', '.join(exporters)}")
    path = exporters[fmt](contract, out)
    console.print(f"[green]Exported {fmt}:[/green] {path}")


@app.command()
def drift(
    old: Path = typer.Option(..., "--old", help="Old profile JSON"),
    new: Path = typer.Option(..., "--new", help="New profile JSON"),
) -> None:
    """Compare two saved profiles."""
    from dqdoctor.drift import compare_profiles, load_profile

    try:
        result = compare_profiles(load_profile(old), load_profile(new))
    except Exception as exc:  # noqa: BLE001
        _fail(f"drift failed: {exc}")
    console.print(f"[bold]{result.summary}[/bold]")
    for d in result.drifts:
        color = {"high": "red", "medium": "yellow", "low": "green"}[d.severity]
        console.print(f"  [{color}]{d.severity.upper()}[/{color}] "
                      f"{d.column}.{d.metric}: {d.change}")


@app.command()
def mcp(
    config: Path | None = typer.Option(None, "--config", help="Config file path"),
) -> None:
    """Run a stdio MCP server (tools: list/profile/check/summary)."""
    try:
        from dqdoctor.mcp_server import serve
    except ImportError as exc:
        _fail(f"MCP extra missing: {exc} (pip install 'dq-doctor[mcp]')")
    serve(config)


@app.command()
def serve(
    report: Path = typer.Option(..., "--report", help="JSON report to serve"),
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8501, "--port"),
) -> None:
    """Serve an existing JSON report as a read-only web page."""
    from dqdoctor.dashboard import run_dashboard

    run_dashboard(report, host=host, port=port)


if __name__ == "__main__":
    app()
