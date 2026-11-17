"""Great Expectations export (contract -> suite JSON).

Targets GX 1.x suite JSON: ``{"version": "1.0", "type":
"ExpectationSuite", "name": ..., "expectations": [{"type": ...,
"kwargs": ...}]}``. The 0.7 exporter emitted the 0.x shape
(``expectation_suite_name`` / ``expectation_type``) which GX 1.x cannot
consume directly. Rule types without a GX expectation are listed in
``meta.unmapped`` so they stay visible.
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
        kwargs = {}
        if rule.params.get("min") is not None:
            kwargs["min_value"] = rule.params["min"]
        if rule.params.get("max") is not None:
            kwargs["max_value"] = rule.params["max"]
        if rule.params.get("exact") is not None:
            kwargs["value"] = rule.params["exact"]
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
            "version": "1.0",
            "type": "ExpectationSuite",
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
