from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any

import yaml

from dqdoctor.models import ProfileResult, RuleSuggestion


def _sanitize(obj):
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize(v) for v in obj]
    return obj


def _rule_to_dbt_test(rule: RuleSuggestion) -> Any | None:
    if rule.rule_type == "not_null":
        return "not_null"
    if rule.rule_type == "unique":
        return "unique"
    if rule.rule_type == "accepted_values":
        return {
            "accepted_values": {
                "values": _sanitize(rule.params.get("values", [])),
            }
        }
    if rule.rule_type == "range":
        min_val = _sanitize(rule.params.get("min"))
        max_val = _sanitize(rule.params.get("max"))
        return [
            {"dbt_utils.expression_is_true": {"expression": f">= {min_val}"}},
            {"dbt_utils.expression_is_true": {"expression": f"<= {max_val}"}},
        ]
    return None


_DBT_UTILS_NOTE = (
    "# Note: range tests use dbt_utils.expression_is_true. "
    "Install dbt-utils package to enable them.\n"
)


def export_dbt_schema(
    profile: ProfileResult,
    rules: list[RuleSuggestion],
) -> str:
    column_models = {}
    for rule in rules:
        dbt_test = _rule_to_dbt_test(rule)
        if dbt_test is None:
            continue
        col = rule.column
        if col not in column_models:
            col_profile = next((c for c in profile.columns if c.name == col), None)
            column_models[col] = {
                "name": col,
                "description": "",
                "meta": {
                    "semantic_type": col_profile.inferred_semantic_type
                    if col_profile
                    else "unknown",
                },
                "tests": [],
            }
        if isinstance(dbt_test, list):
            column_models[col]["tests"].extend(dbt_test)
        else:
            column_models[col]["tests"].append(dbt_test)

    schema = {
        "version": 2,
        "models": [
            {
                "name": profile.table_name,
                "description": "",
                "columns": list(column_models.values()),
            }
        ],
    }
    has_range = any(r.rule_type == "range" for r in rules)
    output = yaml.dump(_sanitize(schema), default_flow_style=False, sort_keys=False)
    if has_range:
        output = _DBT_UTILS_NOTE + output
    return output


def save_dbt_schema(
    profile: ProfileResult,
    rules: list[RuleSuggestion],
    output_path: "str | Path",
) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    content = export_dbt_schema(profile, rules)
    output_path.write_text(content, encoding="utf-8")
    return output_path
