"""Markdown export: contract + column dictionary."""
from __future__ import annotations

from pathlib import Path

from dqdoctor.contract import Contract


def export_markdown(contract: Contract) -> str:
    lines = ["# dq-doctor 1.0 contract", ""]
    lines.append(f"- Datasource: `{contract.datasource or '-'}`")
    lines.append(f"- Generated: {contract.generated_at or '-'}")
    lines.append("")
    for table, tr in sorted(contract.tables.items()):
        lines.append(f"## {table}")
        lines.append("")
        lines.append("| Rule ID | Type | Column | Severity | Params | Enabled |")
        lines.append("|--------|------|--------|----------|--------|---------|")
        for r in tr.rules:
            params = ", ".join(f"{k}={v!r}" for k, v in r.params.items()) or "-"
            lines.append(
                f"| `{r.id}` | {r.type} | {r.column} | {r.severity} "
                f"| {params} | {'yes' if r.enabled else 'no'} |"
            )
        lines.append("")
    return "\n".join(lines) + "\n"


def save(contract: Contract, out: Path) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(export_markdown(contract), encoding="utf-8")
    return out
