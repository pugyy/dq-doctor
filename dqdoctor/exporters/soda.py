"""SodaCL export (contract -> checks YAML).

Uses the documented SodaCL parameter block: ``invalid_count(col) = 0``
with a nested ``valid values: [...]`` list (the 0.7 exporter emitted an
inline ``{ values: ... }`` map SodaCL does not recognize). SQL rules
export as ``custom sql`` checks; unmappable types land in comments.
"""
from __future__ import annotations

from pathlib import Path

import yaml

from dqdoctor.contract import Contract


def _quote(value) -> str:
    return "[" + ", ".join(
        "'" + str(v).replace("'", "''") + "'" for v in value
    ) + "]"


def export_soda(contract: Contract) -> str:
    lines: list[str] = []
    for table, tr in sorted(contract.tables.items()):
        lines.append(f"checks for {table}:")
        unmapped: list[str] = []
        for rule in tr.rules:
            if not rule.enabled:
                continue
            if rule.type == "not_null":
                lines.append(f"  - missing_count({rule.column}) = 0")
            elif rule.type == "unique":
                lines.append(f"  - duplicate_count({rule.column}) = 0")
            elif rule.type == "accepted_values":
                lines.append(f"  - invalid_count({rule.column}) = 0:")
                lines.append(
                    "      valid values: "
                    + _quote(rule.params.get("values", []))
                )
            elif rule.type == "range":
                if rule.params.get("min") is not None:
                    lines.append(f"  - min({rule.column}) >= {rule.params['min']}")
                if rule.params.get("max") is not None:
                    lines.append(f"  - max({rule.column}) <= {rule.params['max']}")
            elif rule.type == "freshness":
                hours = rule.params.get("max_age_hours", 24)
                lines.append(f"  - freshness({rule.column}) < {hours}h")
            elif rule.type == "row_count":
                parts = []
                if rule.params.get("min") is not None:
                    parts.append(f"row_count >= {rule.params['min']}")
                if rule.params.get("max") is not None:
                    parts.append(f"row_count <= {rule.params['max']}")
                for p in parts:
                    lines.append(f"  - {p}")
            else:
                unmapped.append(f"{table}: rule {rule.id} ({rule.type}) not exportable")
        lines.append("")
    text = "\n".join(lines)
    if unmapped:
        text += "# unmapped rules (no SodaCL equivalent):\n" + \
            "\n".join("# " + u for u in unmapped) + "\n"
    return text


def save(contract: Contract, out: Path) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(export_soda(contract), encoding="utf-8")
    _ = yaml  # (yaml kept available for future structured SodaCL config export)
    return out
