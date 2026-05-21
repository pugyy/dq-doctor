from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from dqdoctor.demo import create_demo_db, list_tables
from dqdoctor.exporters.dbt import save_dbt_schema
from dqdoctor.exporters.gx import save_gx_suite
from dqdoctor.exporters.markdown import save_markdown
from dqdoctor.models import ProfileResult
from dqdoctor.profiler import profile_table
from dqdoctor.reporter import build_report, save_html
from dqdoctor.rule_engine import generate_rules
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
) -> None:
    db_path = create_demo_db(output)
    tables = list_tables(db_path)
    console.print(f"[green]Demo database created:[/green] {db_path}")
    console.print(f"[blue]Tables:[/blue] {', '.join(tables)}")
    console.print(
        f"[dim]Try: dqdoctor check --db {db_path} "
        f"--table {tables[0]}[/dim]"
    )


@app.command()
def tables(
    db: str = typer.Option(..., "--db", help="Path to DuckDB database"),
) -> None:
    table_list = list_tables(db)
    for t in table_list:
        console.print(f"  {t}")
    console.print(f"[dim]{len(table_list)} table(s)[/dim]")


def _print_profile(profile: ProfileResult) -> None:
    table = Table(
        title=f"Profile: {profile.table_name} ({profile.row_count} rows)"
    )
    table.add_column("Column", style="bold")
    table.add_column("Type")
    table.add_column("Null Rate", justify="right")
    table.add_column("Distinct Rate", justify="right")
    table.add_column("Min")
    table.add_column("Max")
    table.add_column("Semantic")

    for col in profile.columns:
        table.add_row(
            col.name,
            col.dtype,
            f"{col.null_rate:.2%}",
            f"{col.distinct_rate:.2%}",
            str(col.min_value) if col.min_value is not None else "-",
            str(col.max_value) if col.max_value is not None else "-",
            col.inferred_semantic_type,
        )
    console.print(table)


def _run_check(
    db: str,
    table: str,
    out: str,
    ci: bool = False,
    max_failures: int = 0,
    llm_key: Optional[str] = None,
    llm_base_url: Optional[str] = None,
    llm_model: str = "deepseek-chat",
) -> int:
    with console.status("[bold blue]Profiling table..."):
        profile_result = profile_table(db, table)

    with console.status("[bold blue]Generating rules..."):
        rules = generate_rules(
            profile_result,
            llm_key=llm_key,
            llm_base_url=llm_base_url,
            llm_model=llm_model,
        )

    with console.status("[bold blue]Validating..."):
        results = validate_rules(db, table, rules)

    report = build_report(profile_result, rules, results)
    report_path = save_html(report, out)

    console.print()
    console.print(
        f"[bold]{table}[/bold]: "
        f"Rules {report.total_rules}  "
        f"[green]Passed {report.passed_rules}[/green]  "
        f"[red]Failed {report.failed_rules}[/red]"
    )

    for r in results:
        icon = "[green]PASS[/green]" if r.passed else "[red]FAIL[/red]"
        console.print(f"  {icon} {r.rule_type} on {r.column}: {r.message}")

    console.print(f"[dim]Report: {report_path}[/dim]")
    console.print()

    if ci and report.failed_rules > max_failures:
        return report.failed_rules
    return 0


@app.command()
def profile(
    db: str = typer.Option(..., "--db", help="Path to DuckDB database"),
    table: str = typer.Option(..., "--table", help="Table name to profile"),
    out: Optional[str] = typer.Option(
        None, "--out", help="Output JSON path"
    ),
) -> None:
    profile_result = profile_table(db, table)
    _print_profile(profile_result)

    if out:
        out_path = Path(out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            profile_result.model_dump_json(indent=2), encoding="utf-8"
        )
        console.print(f"[green]Profile saved to:[/green] {out_path}")


@app.command()
def check(
    db: str = typer.Option(..., "--db", help="Path to DuckDB database"),
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
) -> None:
    if all_tables:
        table_list = list_tables(db)
        if not table_list:
            console.print("[yellow]No tables found.[/yellow]")
            raise typer.Exit(0)
        total_failures = 0
        for i, t in enumerate(table_list):
            table_out = str(Path(out).with_name(
                f"{Path(out).stem}_{t}{Path(out).suffix}"
            ))
            failures = _run_check(
                db, t, table_out, ci=ci, max_failures=max_failures,
                llm_key=llm_key, llm_base_url=llm_base_url,
                llm_model=llm_model,
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
            db, table, out, ci=ci, max_failures=max_failures,
            llm_key=llm_key, llm_base_url=llm_base_url,
            llm_model=llm_model,
        )
        if ci and failures > 0:
            raise typer.Exit(1)


_EXPORT_FORMATS = {
    "dbt": save_dbt_schema,
    "gx": save_gx_suite,
    "markdown": save_markdown,
}


@app.command()
def export(
    db: str = typer.Option(..., "--db", help="Path to DuckDB database"),
    table: str = typer.Option(..., "--table", help="Table name to export"),
    fmt: str = typer.Option(
        ..., "--format",
        help="Export format: dbt, gx, markdown",
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
    rules = generate_rules(profile_result)
    exporter = _EXPORT_FORMATS[fmt]
    output_path = exporter(profile_result, rules, out)
    console.print(f"[green]Exported {fmt} to:[/green] {output_path}")


if __name__ == "__main__":
    app()
