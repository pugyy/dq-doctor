from __future__ import annotations

import json
from pathlib import Path

from dqdoctor.models import RuleSuggestion


def load_custom_rules(path: "str | Path") -> list[RuleSuggestion]:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Rules file not found: {path}")

    content = path.read_text(encoding="utf-8-sig")
    if path.suffix in (".yaml", ".yml"):
        import yaml
        data = yaml.safe_load(content)
    else:
        data = json.loads(content)

    if not isinstance(data, dict):
        raise ValueError("Rules file must be a dict with a 'rules' key")

    raw_rules = data.get("rules", [])
    if not isinstance(raw_rules, list):
        raise ValueError("'rules' must be a list")

    rules: list[RuleSuggestion] = []
    for i, raw in enumerate(raw_rules):
        if not raw.get("enabled", True):
            continue
        rules.append(RuleSuggestion(
            rule_id=raw.get("rule_id", f"custom.{i}"),
            rule_type=raw.get("rule_type", "unknown"),
            column=raw.get("column", ""),
            params=raw.get("params", {}),
            confidence=float(raw.get("confidence", 0.5)),
            severity=raw.get("severity", "medium"),
            reason=raw.get("reason", ""),
            source="custom",
        ))
    return rules


def merge_rules(
    auto_rules: list[RuleSuggestion],
    custom_rules: list[RuleSuggestion],
) -> list[RuleSuggestion]:
    seen = set()
    merged: list[RuleSuggestion] = []
    for r in auto_rules:
        key = (r.rule_type, r.column)
        if key not in seen:
            seen.add(key)
            merged.append(r)
    for r in custom_rules:
        key = (r.rule_type, r.column, r.source)
        if key not in seen:
            seen.add(key)
            merged.append(r)
    return merged
