"""Deequ export (contract -> constraint mapping JSON).

Deequ has no official JSON interchange format; the consumer of this file
is **pydeequ script authors** - each entry carries the pydeequ constraint
class and constructor kwargs so a short script can rebuild the
``ConstraintSuggestions``/``VerificationSuite``. Unmappable rules are
listed explicitly.
"""
from __future__ import annotations

import json
from pathlib import Path

from dqdoctor.contract import Contract


def _constraint(rule) -> dict | None:
    if rule.type == "not_null":
        return {"constraint": "HasCompleteness", "kwargs": {"column": rule.column}}
    if rule.type == "unique":
        return {"constraint": "IsUnique", "kwargs": {"column": rule.column}}
    if rule.type == "accepted_values":
        return {"constraint": "IsContainedIn",
                "kwargs": {"column": rule.column,
                           "allowed_values": list(rule.params.get("values", []))}}
    if rule.type == "range":
        return {"constraint": "IsBetween",
                "kwargs": {"column": rule.column,
                           "lower": rule.params.get("min"),
                           "upper": rule.params.get("max")}}
    if rule.type == "regex":
        return {"constraint": "MatchesPattern",
                "kwargs": {"column": rule.column,
                           "pattern": rule.params.get("pattern", "")}}
    if rule.type == "row_count":
        return {"constraint": "HasSize",
                "kwargs": {"min_size": rule.params.get("min"),
                           "max_size": rule.params.get("max")}}
    return None


def export_deequ(contract: Contract) -> str:
    datasets = []
    for table, tr in sorted(contract.tables.items()):
        checks = []
        unmapped = []
        for rule in tr.rules:
            if not rule.enabled:
                continue
            mapped = _constraint(rule)
            if mapped is None:
                unmapped.append(rule.id)
                continue
            mapped["rule_id"] = rule.id
            checks.append(mapped)
        datasets.append({
            "dataset": table,
            "engine": "pydeequ",
            "checks": checks,
            "unmapped_rule_ids": unmapped,
        })
    return json.dumps({"version": "1.0", "generated_by": "dq-doctor 1.0",
                       "datasets": datasets}, indent=2, ensure_ascii=False)


def save(contract: Contract, out: Path) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(export_deequ(contract), encoding="utf-8")
    return out
