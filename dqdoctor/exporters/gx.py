"""Great Expectations export (contract -> suite JSON).

Each entry in ``suites`` can be passed to ``gx.ExpectationSuite(**entry)``.
Rule types without a GX expectation are listed in ``meta.unmapped_rule_ids``.
"""
from __future__ import annotations

import json
from pathlib import Path

from dqdoctor.contract import Contract


def _expectation(rule) -> dict | None:
    if rule.type == "not_null":
        return {"type": "expect_column_values_to_not_be_null",
                "kwargs": {"column": rule.column}}
    if rule.type == "unique":
        return {"type": "expect_column_values_to_be_unique",
                "kwargs": {"column": rule.column}}
    if rule.type == "accepted_values":
        return {"type": "expect_column_values_to_be_in_set",
                "kwargs": {"column": rule.column,
                           "value_set": list(rule.params.get("values", []))}}
    if rule.type == "range":
        kwargs = {"column": rule.column}
        if rule.params.get("min") is not None:
            kwargs["min_value"] = rule.params["min"]
        if rule.params.get("max") is not None:
            kwargs["max_value"] = rule.params["max"]
        return {"type": "expect_column_values_to_be_between", "kwargs": kwargs}
    if rule.type == "regex":
        return {"type": "expect_column_values_to_match_regex",
                "kwargs": {"column": rule.column,
                           "regex": rule.params.get("pattern", "")}}
    if rule.type == "row_count":
        if rule.params.get("exact") is not None:
            if rule.params.get("min") is not None or rule.params.get("max") is not None:
                return None
            return {"type": "expect_table_row_count_to_equal",
                    "kwargs": {"value": rule.params["exact"]}}
        kwargs = {}
        if rule.params.get("min") is not None:
            kwargs["min_value"] = rule.params["min"]
        if rule.params.get("max") is not None:
            kwargs["max_value"] = rule.params["max"]
        return {"type": "expect_table_row_count_to_be_between", "kwargs": kwargs}
    return None


def export_gx(contract: Contract) -> str:
    suites = []
    for table, tr in sorted(contract.tables.items()):
        expectations = []
        unmapped = []
        for rule in tr.rules:
            if not rule.enabled:
                continue
            exp = _expectation(rule)
            if exp is None:
                unmapped.append(rule.id)
                continue
            exp["meta"] = {"severity": rule.severity, "source": "dq-doctor"}
            expectations.append(exp)
        suites.append({
            "name": f"{table}.suite",
            "expectations": expectations,
            "meta": {
                "generated_by": "dq-doctor 1.0",
                "unmapped_rule_ids": unmapped,
            },
        })
    return json.dumps({"suites": suites}, indent=2, ensure_ascii=False)


def save(contract: Contract, out: Path) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(export_gx(contract), encoding="utf-8")
    return out
