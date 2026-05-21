from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

from dqdoctor.models import ProfileResult, RuleSuggestion


def _rule_to_expectation(rule: RuleSuggestion) -> dict[str, Any] | None:
    if rule.rule_type == "not_null":
        return {
            "expectation_type": "expect_column_values_to_not_be_null",
            "kwargs": {"column": rule.column},
        }
    if rule.rule_type == "unique":
        return {
            "expectation_type": "expect_column_values_to_be_unique",
            "kwargs": {"column": rule.column},
        }
    if rule.rule_type == "accepted_values":
        return {
            "expectation_type": "expect_column_values_to_be_in_set",
            "kwargs": {
                "column": rule.column,
                "value_set": rule.params.get("values", []),
            },
        }
    if rule.rule_type == "range":
        return {
            "expectation_type": "expect_column_values_to_be_between",
            "kwargs": {
                "column": rule.column,
                "min_value": rule.params.get("min"),
                "max_value": rule.params.get("max"),
            },
        }
    return None


def export_gx_suite(
    profile: ProfileResult,
    rules: list[RuleSuggestion],
) -> str:
    expectations = []
    for rule in rules:
        exp = _rule_to_expectation(rule)
        if exp is not None:
            exp["meta"] = {
                "confidence": rule.confidence,
                "severity": rule.severity,
                "reason": rule.reason,
                "source": rule.source,
            }
            expectations.append(exp)

    suite = {
        "expectation_suite_name": f"{profile.table_name}.suite",
        "expectations": expectations,
        "meta": {
            "table_name": profile.table_name,
            "row_count": profile.row_count,
            "generated_by": "dq-doctor",
        },
    }
    return json.dumps(suite, indent=2, ensure_ascii=False, default=_json_default)


def _json_default(obj):
    if isinstance(obj, Decimal):
        return float(obj)
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def save_gx_suite(
    profile: ProfileResult,
    rules: list[RuleSuggestion],
    output_path: "str | Path",
) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    content = export_gx_suite(profile, rules)
    output_path.write_text(content, encoding="utf-8")
    return output_path
