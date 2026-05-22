from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import typer
from rich.console import Console
from rich.table import Table

from dqdoctor.custom_rules import (
    load_custom_rules,
    load_disabled_keys,
    load_severity_overrides,
    merge_rules,
)
from dqdoctor.demo import create_demo_db, create_dirty_db, list_tables
from dqdoctor.exporters.dbt import save_dbt_schema
from dqdoctor.exporters.deequ import save_deequ
from dqdoctor.exporters.gx import save_gx_suite
from dqdoctor.exporters.markdown import save_markdown
from dqdoctor.exporters.soda import save_soda_cl
from dqdoctor.profiler import profile_table
from dqdoctor.reporter import build_report, save_html
from dqdoctor.rule_engine import generate_rules
from dqdoctor.sql_rules import execute_sql_rules
from dqdoctor.validator import validate_rules

app = typer.Typer(
    name="dqdoctor",
    help="A lightweight data quality checkup CLI. No YAML, no rule syntax to remember.",
    add_completion=False,
)
console = Console()


@app.command()
def demo(
    output: Optional[str] = typer.Option(
        None, "--output", "-o", help="Output DuckDB path"
    ),
    dirty: bool = typer.Option(
        False, "--dirty", help="Generate dirty demo with intentional data quality issues"
    ),
) -> None:
    if dirty:
        db_path = create_dirty_db(output)
        console.print("[yellow]Dirty demo database created (contains issues!):[/yellow]")
    else:
        db_path = create_demo_db(output)
        console.print(f"[green]Demo database created:[/green] {db_path}")
    tables = list_tables(db_path)
    console.print(f"[blue]Tables:[/blue] {', '.join(tables)}")
    console.print(
        f"[dim]Try: dqdoctor check --db {db_path} "
        f"--table {tables[0]}[/dim]"
    )


@app.command()
def tables(
    db: Optional[str] = typer.Option(
        None, "--db", help="Path to database"
    ),
    config: Optional[str] = typer.Option(
        None, "--config", help="Path to .dqdoctor.yml config file"
    ),
) -> None:
    from dqdoctor.config import load_config as _load_config
    effective_db = _load_config(config).db or db
    if not effective_db:
        console.print("[red]Error: --db is required.[/red]")
        raise typer.Exit(1)
    table_list = list_tables(effective_db)
    for t in table_list:
        console.print(f"  {t}")
    console.print(f"[dim]{len(table_list)} table(s)[/dim]")


def _print_profile(profile_result) -> None:
    table = Table(
        title=f"Profile: {profile_result.table_name} ({profile_result.row_count} rows)"
    )
    table.add_column("Column", style="bold")
    table.add_column("Type")
    table.add_column("Null Rate", justify="right")
    table.add_column("Distinct Rate", justify="right")
    table.add_column("Min")
    table.add_column("Max")
    table.add_column("Semantic")
    table.add_column("PII")

    for col in profile_result.columns:
        pii_label = f"[red]{col.pii_type}[/red]" if col.pii_type else "-"
        table.add_row(
            col.name,
            col.dtype,
            f"{col.null_rate:.2%}",
            f"{col.distinct_rate:.2%}",
            str(col.min_value) if col.min_value is not None else "-",
            str(col.max_value) if col.max_value is not None else "-",
            col.inferred_semantic_type,
            pii_label,
        )
    console.print(table)


@app.command()
def profile(
    db: str = typer.Option(..., "--db", help="Path to database"),
    table: str = typer.Option(..., "--table", help="Table name to profile"),
    out: Optional[str] = typer.Option(
        None, "--out", help="Output JSON path (saves profile for drift comparison)"
    ),
) -> None:
    from dqdoctor.drift import save_profile

    profile_result = profile_table(db, table)
    _print_profile(profile_result)

    if out:
        out_path = Path(out)
        save_profile(profile_result, out_path)
        console.print(f"[green]Profile saved to:[/green] {out_path}")


def _run_check(
    db: str,
    table: str,
    out: str,
    ci: bool = False,
    max_failures: int = 0,
    llm_key: Optional[str] = None,
    llm_base_url: Optional[str] = None,
    llm_model: str = "deepseek-chat",
    rules_file: Optional[str] = None,
    config: Any = None,
    save_profile_dir: Optional[str] = None,
    verbose_rules: bool = False,
) -> int:
    from dqdoctor.config import apply_config_to_rules, get_sql_rules

    with console.status("[bold blue]Profiling table..."):
        profile_result = profile_table(db, table)

    if save_profile_dir:
        from datetime import datetime

        from dqdoctor.drift import save_profile

        pdir = Path(save_profile_dir)
        pdir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        ppath = pdir / f"{table}_{ts}.json"
        save_profile(profile_result, ppath)
        console.print(f"[dim]Profile saved to {ppath}[/dim]")

    with console.status("[bold blue]Generating rules..."):
        rules = generate_rules(
            profile_result,
            llm_key=llm_key,
            llm_base_url=llm_base_url,
            llm_model=llm_model,
        )

    if config:
        rules, config_log = apply_config_to_rules(rules, table, config)
    else:
        config_log = []

    if rules_file:
        try:
            custom = load_custom_rules(rules_file)
            disabled = load_disabled_keys(rules_file)
            sev_overrides = load_severity_overrides(rules_file)
            rules = merge_rules(rules, custom, disabled, sev_overrides)
            n_disabled = len(disabled)
            msg = f"Loaded {len(custom)} rules from {rules_file}"
            if n_disabled:
                msg += f" ({n_disabled} disabled)"
            console.print(f"[dim]{msg}[/dim]")
        except FileNotFoundError:
            console.print(f"[yellow]Rules file not found: {rules_file}[/yellow]")
        except Exception as e:
            console.print(f"[red]Error loading rules file: {e}[/red]")

    with console.status("[bold blue]Validating..."):
        results = validate_rules(db, table, rules)

    sql_rule_defs = []
    if config:
        sql_rule_defs = get_sql_rules(config, table)
    if sql_rule_defs:
        from dqdoctor.models import RuleSuggestion

        with console.status("[bold blue]Running SQL rules..."):
            sql_results = execute_sql_rules(db, table, sql_rule_defs)
            results.extend(sql_results)
            for sr in sql_results:
                rules.append(RuleSuggestion(
                    rule_id=sr.rule_id,
                    rule_type="sql",
                    column="*",
                    confidence=0.9,
                    severity="medium",
                    reason=sr.message,
                    source="config",
                ))

    from dqdoctor.models import PIIFinding, RefIntegrityIssue

    pii_findings = [
        PIIFinding(column=c.name, pii_type=c.pii_type, sample_count=0)
        for c in profile_result.columns if c.pii_type
    ]

    refint_issues = []
    with console.status("[bold blue]Checking referential integrity..."):
        try:
            from dqdoctor.models import RefIntegrityIssue
            from dqdoctor.ref_integrity import check_referential_integrity

            ri_results = check_referential_integrity(db)
            for ri in ri_results:
                if ri.from_table == table or ri.to_table == table:
                    refint_issues.append(RefIntegrityIssue(
                        from_table=ri.from_table,
                        from_column=ri.from_column,
                        to_table=ri.to_table,
                        to_column=ri.to_column,
                        orphan_rows=ri.orphan_rows,
                        total_rows=ri.total_rows,
                        sample_orphans=ri.sample_orphans,
                    ))
        except Exception:
            pass

    report = build_report(
        profile_result, rules, results,
        pii_findings=pii_findings,
        refint_issues=refint_issues,
    )
    report_path = save_html(report, out)

    score_color = (
        "green" if report.quality_score >= 80
        else "yellow" if report.quality_score >= 50
        else "red"
    )

    console.print()
    console.print(
        f"[bold]{table}[/bold]: "
        f"Score [{score_color}]{report.quality_score}/100[/{score_color}]  "
        f"Rules {report.total_rules}  "
        f"[green]Passed {report.passed_rules}[/green]  "
        f"[red]Failed {report.failed_rules}[/red]  "
        f"[cyan]Suggested {report.suggested_rules}[/cyan]"
    )

    for r in results:
        if r.total_count == 0 and r.passed:
            icon = "[cyan]SUGGEST[/cyan]"
        else:
            icon = "[green]PASS[/green]" if r.passed else "[red]FAIL[/red]"
        console.print(f"  {icon} {r.rule_type} on {r.column}: {r.message}")

    if verbose_rules:
        console.print("[dim]Rule sources:[/dim]")
        for r in rules:
            source_label = r.source if r.source != "heuristic" else "auto"
            console.print(
                f"  [dim]{r.rule_type}.{r.column}: {source_label} "
                f"(severity={r.severity})[/dim]"
            )
        for log_line in config_log:
            console.print(f"  [dim]{log_line}[/dim]")
        if rules_file:
            disabled = load_disabled_keys(rules_file)
            for rk in disabled:
                console.print(
                    f"  [dim]{rk[0]}.{rk[1]}: disabled by {rules_file}[/dim]"
                )

    if pii_findings:
        console.print("[yellow]PII detected:[/yellow]")
        for p in pii_findings:
            console.print(f"  [red]{p.pii_type}[/red] in column '{p.column}'")

    for ri in refint_issues:
        if ri.orphan_rows > 0:
            console.print(
                f"  [red]ORPHAN[/red] {ri.from_table}.{ri.from_column} -> "
                f"{ri.to_table}.{ri.to_column}: "
                f"{ri.orphan_rows}/{ri.total_rows} orphans"
            )

    console.print(f"[dim]Report: {report_path}[/dim]")
    console.print()

    if ci:
        refint_fails = sum(1 for ri in refint_issues if ri.orphan_rows > 0)
        total_fails = report.failed_rules + refint_fails
        if total_fails > max_failures:
            return total_fails
    return 0


@app.command()
def check(
    db: Optional[str] = typer.Option(
        None, "--db", help="Path to database (or set in .dqdoctor.yml)"
    ),
    table: Optional[str] = typer.Option(
        None, "--table", help="Table name to check"
    ),
    all_tables: bool = typer.Option(
        False, "--all-tables", help="Check all tables in the database"
    ),
    out: str = typer.Option(
        "report.html", "--out", help="Output HTML report path"
    ),
    ci: bool = typer.Option(
        False, "--ci", help="CI mode: exit with non-zero code on failures"
    ),
    max_failures: int = typer.Option(
        0, "--max-failures", help="Max allowed failures (CI mode only)"
    ),
    llm_key: Optional[str] = typer.Option(
        None, "--llm-key", help="LLM API key for enhanced rules"
    ),
    llm_base_url: Optional[str] = typer.Option(
        None, "--llm-base-url", help="LLM API base URL"
    ),
    llm_model: str = typer.Option(
        "deepseek-chat", "--llm-model", help="LLM model name"
    ),
    rules: Optional[str] = typer.Option(
        None, "--rules", help="Path to custom rules file (JSON/YAML)"
    ),
    config: Optional[str] = typer.Option(
        None, "--config", help="Path to .dqdoctor.yml config file"
    ),
    save_profile: Optional[str] = typer.Option(
        None, "--save-profile",
        help="Directory to save profile JSON for drift comparison"
    ),
    verbose_rules: bool = typer.Option(
        False, "--verbose-rules",
        help="Show rule source and override details"
    ),
) -> None:
    from dqdoctor.config import load_config

    dq_config = load_config(config)
    effective_db = dq_config.db or db
    if not effective_db:
        console.print(
            "[red]Error: --db is required (or set db in .dqdoctor.yml).[/red]"
        )
        raise typer.Exit(1)
    if all_tables:
        table_list = list_tables(effective_db)
        if not table_list:
            console.print("[yellow]No tables found.[/yellow]")
            raise typer.Exit(0)
        total_failures = 0
        for i, t in enumerate(table_list):
            table_out = str(Path(out).with_name(
                f"{Path(out).stem}_{t}{Path(out).suffix}"
            ))
            failures = _run_check(
                effective_db, t, table_out, ci=ci, max_failures=max_failures,
                llm_key=llm_key, llm_base_url=llm_base_url,
                llm_model=llm_model, rules_file=rules,
                config=dq_config, save_profile_dir=save_profile,
                verbose_rules=verbose_rules,
            )
            total_failures += failures
        if ci and total_failures > 0:
            console.print(
                f"[red]CI: {total_failures} total failures, "
                f"threshold is {max_failures}.[/red]"
            )
            raise typer.Exit(1)
    else:
        if not table:
            console.print(
                "[red]Error: --table is required when --all-tables is not set.[/red]"
            )
            raise typer.Exit(1)
        failures = _run_check(
            effective_db, table, out, ci=ci, max_failures=max_failures,
            llm_key=llm_key, llm_base_url=llm_base_url,
            llm_model=llm_model, rules_file=rules,
            config=dq_config, save_profile_dir=save_profile,
            verbose_rules=verbose_rules,
        )
        if ci and failures > 0:
            raise typer.Exit(1)


_EXPORT_FORMATS = {
    "dbt": save_dbt_schema,
    "gx": save_gx_suite,
    "markdown": save_markdown,
    "soda": save_soda_cl,
    "deequ": save_deequ,
}


@app.command()
def export(
    db: str = typer.Option(..., "--db", help="Path to DuckDB database"),
    table: str = typer.Option(..., "--table", help="Table name to export"),
    fmt: str = typer.Option(
        ..., "--format",
        help="Export format: dbt, gx, markdown, soda, deequ",
    ),
    out: str = typer.Option(
        ..., "--out", help="Output file path",
    ),
) -> None:
    if fmt not in _EXPORT_FORMATS:
        console.print(
            f"[red]Unknown format '{fmt}'. "
            f"Choose from: {', '.join(_EXPORT_FORMATS)}[/red]"
        )
        raise typer.Exit(1)

    profile_result = profile_table(db, table)
    gen_rules = generate_rules(profile_result)
    exporter = _EXPORT_FORMATS[fmt]
    output_path = exporter(profile_result, gen_rules, out)
    console.print(f"[green]Exported {fmt} to:[/green] {output_path}")


@app.command()
def fk(
    db: str = typer.Option(..., "--db", help="Path to DuckDB database"),
    min_overlap: float = typer.Option(
        0.5, "--min-overlap", help="Minimum overlap rate threshold"
    ),
) -> None:
    from dqdoctor.fk_discovery import discover_foreign_keys

    with console.status("[bold blue]Discovering foreign keys..."):
        relationships = discover_foreign_keys(db, min_overlap=min_overlap)

    if not relationships:
        console.print("[yellow]No foreign key relationships found.[/yellow]")
        return

    table = Table(title="Discovered Foreign Keys")
    table.add_column("From", style="bold")
    table.add_column("To", style="bold")
    table.add_column("Overlap", justify="right")
    table.add_column("Confidence", justify="right")

    for rel in relationships:
        table.add_row(
            f"{rel.from_table}.{rel.from_column}",
            f"{rel.to_table}.{rel.to_column}",
            f"{rel.overlap_rate:.0%}",
            f"{rel.confidence:.0%}",
        )
    console.print(table)


@app.command()
def correlate(
    db: str = typer.Option(..., "--db", help="Path to DuckDB database"),
    table: str = typer.Option(..., "--table", help="Table name"),
) -> None:
    from dqdoctor.correlation import detect_correlations

    with console.status("[bold blue]Detecting correlations..."):
        corrs = detect_correlations(db, table)

    if not corrs:
        console.print("[yellow]No significant correlations found.[/yellow]")
        return

    for c in corrs:
        console.print(
            f"  [{c.correlation_type}] {c.description} "
            f"(confidence: {c.confidence:.0%})"
        )


@app.command()
def drift(
    old: str = typer.Option(..., "--old", help="Path to old profile JSON"),
    new: str = typer.Option(..., "--new", help="Path to new profile JSON"),
) -> None:
    from dqdoctor.drift import compare_profiles, load_profile

    old_profile = load_profile(old)
    new_profile = load_profile(new)
    result = compare_profiles(old_profile, new_profile)

    console.print(f"[bold]{result.summary}[/bold]")
    for d in result.drifts:
        color = {"high": "red", "medium": "yellow", "low": "green"}[d.severity]
        console.print(
            f"  [{color}]{d.severity.upper()}[/{color}] "
            f"{d.column}.{d.metric}: {d.change}"
        )


@app.command()
def lineage(
    db: str = typer.Option(..., "--db", help="Path to DuckDB database"),
) -> None:
    from dqdoctor.lineage import discover_lineage

    with console.status("[bold blue]Discovering lineage..."):
        result = discover_lineage(db)

    if not result.edges:
        console.print("[yellow]No lineage edges found.[/yellow]")
        return

    console.print(f"[bold]{result.summary}[/bold]")
    for edge in result.edges:
        icon = "FK" if edge.lineage_type == "foreign_key" else "CORR"
        console.print(
            f"  [{icon}] {edge.description} "
            f"(confidence: {edge.confidence:.0%})"
        )


@app.command()
def serve(
    db: str = typer.Option(..., "--db", help="Path to DuckDB database"),
    host: str = typer.Option("127.0.0.1", "--host", help="Host to bind"),
    port: int = typer.Option(8501, "--port", help="Port to bind"),
) -> None:
    from dqdoctor.dashboard import run_dashboard
    run_dashboard(db, host=host, port=port)


@app.command()
def refint(
    db: str = typer.Option(..., "--db", help="Path to DuckDB database"),
) -> None:
    from dqdoctor.ref_integrity import check_referential_integrity

    with console.status("[bold blue]Checking referential integrity..."):
        results = check_referential_integrity(db)

    if not results:
        console.print("[yellow]No foreign key relationships found.[/yellow]")
        return

    for r in results:
        icon = "[green]PASS[/green]" if r.passed else "[red]FAIL[/red]"
        console.print(
            f"  {icon} {r.from_table}.{r.from_column} → "
            f"{r.to_table}.{r.to_column}: "
            f"{r.orphan_rows}/{r.total_rows} orphans"
        )
        if r.sample_orphans:
            samples = ", ".join(str(v) for v in r.sample_orphans[:5])
            console.print(f"       Sample orphans: [{samples}]")


@app.command("rules-init")
def rules_init(
    db: str = typer.Option(..., "--db", help="Path to database"),
    table: str = typer.Option(..., "--table", help="Table name"),
    out: str = typer.Option("rules.yml", "--out", help="Output rules file path"),
) -> None:
    import yaml as _yaml

    profile_result = profile_table(db, table)
    rules = generate_rules(profile_result)

    def _serialize_params(params: dict) -> dict:
        from decimal import Decimal
        result = {}
        for k, v in params.items():
            if isinstance(v, Decimal):
                result[k] = float(v)
            elif isinstance(v, float):
                result[k] = round(v, 4)
            else:
                result[k] = v
        return result

    rules_data = {
        "table": table,
        "db": db,
        "rules": [
            {
                "rule_id": r.rule_id,
                "rule_type": r.rule_type,
                "column": r.column,
                "params": _serialize_params(r.params),
                "confidence": round(r.confidence, 2),
                "severity": r.severity,
                "reason": r.reason,
                "enabled": True,
            }
            for r in rules
        ],
    }

    out_path = Path(out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        _yaml.dump(rules_data, default_flow_style=False, allow_unicode=True),
        encoding="utf-8",
    )
    console.print(f"[green]Generated {len(rules)} rules for '{table}'[/green]")
    console.print(f"[green]Saved to:[/green] {out_path}")
    console.print("[dim]Edit the file to enable/disable rules, change severity, then:")
    console.print(f"[dim]  dqdoctor check --db {db} --table {table} --rules {out}[/dim]")


@app.command()
def doctor() -> None:
    import importlib
    import sys

    console.print("[bold]dq-doctor health check[/bold]\n")

    checks: list[tuple[str, bool, str]] = []

    py_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    py_ok = sys.version_info >= (3, 9)
    checks.append(("Python version", py_ok, f"{py_ver} {'OK' if py_ok else 'FAIL: need 3.9+'}"))

    pkg_version = "unknown"
    try:
        from dqdoctor import __version__
        pkg_version = __version__
    except Exception:
        pass
    checks.append(("dq-doctor version", True, pkg_version))

    try:
        import duckdb
        checks.append(("DuckDB", True, duckdb.__version__))
    except ImportError:
        checks.append(("DuckDB", False, "not installed"))

    template_ok = (Path(__file__).parent / "templates" / "report.html").exists()
    checks.append(("Report template", template_ok, "OK" if template_ok else "MISSING"))

    seed_ok = (Path(__file__).parent / "data" / "seed.sql").exists()
    checks.append(("Demo data (seed.sql)", seed_ok, "OK" if seed_ok else "MISSING"))

    config_path = Path(".dqdoctor.yml")
    config_ok = config_path.exists()
    config_msg = (
        str(config_path.resolve())
        if config_ok
        else "not found (optional, run dqdoctor init)"
    )
    checks.append(("Config file", config_ok, config_msg))

    non_core_prefixes = ("SQLAlchemy", "psycopg2", "pymysql", "OpenAI", "Flask")
    optional = [
        ("SQLAlchemy", "sqlalchemy", "sql"),
        ("psycopg2", "psycopg2", "sql"),
        ("pymysql", "pymysql", "sql"),
        ("OpenAI", "openai", "llm"),
        ("Flask", "flask", "dashboard"),
    ]
    for label, mod_name, extra in optional:
        display_label = f"{label} \\[{extra}]"
        try:
            m = importlib.import_module(mod_name)
            ver = getattr(m, "__version__", "installed")
            checks.append((display_label, True, ver))
        except ImportError:
            install_hint = f"pip install dq-doctor\\[{extra}]"
            checks.append((display_label, False, f"not installed ({install_hint})"))

    core_ok = True
    table = Table()
    table.add_column("Check", style="bold")
    table.add_column("Status")
    table.add_column("Detail")
    for name, ok, detail in checks:
        is_optional = name.startswith(non_core_prefixes) or name == "Config file"
        icon = (
            "[green]OK[/green]" if ok
            else "[yellow]--[/yellow]" if is_optional
            else "[red]MISS[/red]"
        )
        if not ok and not is_optional:
            core_ok = False
            core_ok = False
        table.add_row(name, icon, detail)
    console.print(table)

    if core_ok:
        console.print("\n[green]All core checks passed.[/green]")
    else:
        console.print("\n[red]Some core checks failed.[/red]")
        console.print("[dim]Try: pip install --upgrade dq-doctor[/dim]")


@app.command()
def init() -> None:
    config_content = """\
# dq-doctor configuration
db: examples/ecommerce/demo.duckdb

tables:
  orders:
    freshness:
      created_at:
        max_age_hours: 48
    disable_rules:
      - range:user_id
    severity:
      order_id:not_null: high
    sql_rules:
      - name: order_amount_positive
        query: "SELECT COUNT(*) FROM orders WHERE total_amount <= 0"
        expect: 0
"""
    Path(".dqdoctor.yml").write_text(config_content, encoding="utf-8")
    console.print("[green]Created .dqdoctor.yml[/green]")
    console.print("[dim]Edit it to configure your project.[/dim]")


if __name__ == "__main__":
    app()
