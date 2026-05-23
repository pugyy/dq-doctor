from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

from dqdoctor.models import ProfileResult, RuleSuggestion


def _sanitize(obj: Any) -> Any:
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize(v) for v in obj]
    return obj


def export_deequ(
    profile: ProfileResult,
    rules: list[RuleSuggestion],
) -> str:
    checks = []
    for rule in rules:
        col = rule.column
        if rule.rule_type == "not_null":
            checks.append(
                {
                    "check": "isComplete",
                    "column": col,
                }
            )
        elif rule.rule_type == "unique":
            checks.append(
                {
                    "check": "isUnique",
                    "column": col,
                }
            )
        elif rule.rule_type == "accepted_values":
            checks.append(
                {
                    "check": "isContainedIn",
                    "column": col,
                    "values": _sanitize(rule.params.get("values", [])),
                }
            )
        elif rule.rule_type == "range":
            min_v = _sanitize(rule.params.get("min"))
            max_v = _sanitize(rule.params.get("max"))
            if min_v is not None and max_v is not None:
                checks.append(
                    {
                        "check": "isBetween",
                        "column": col,
                        "min": min_v,
                        "max": max_v,
                    }
                )

    suite = {
        "dataset": profile.table_name,
        "checks": _sanitize(checks),
    }
    return json.dumps(suite, indent=2, ensure_ascii=False)


def save_deequ(
    profile: ProfileResult,
    rules: list[RuleSuggestion],
    output_path: "str | Path",
) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(export_deequ(profile, rules), encoding="utf-8")
    return output_path
