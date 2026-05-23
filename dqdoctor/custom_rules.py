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
        rules.append(
            RuleSuggestion(
                rule_id=raw.get("rule_id", f"custom.{i}"),
                rule_type=raw.get("rule_type", "unknown"),
                column=raw.get("column", ""),
                params=raw.get("params", {}),
                confidence=float(raw.get("confidence", 0.5)),
                severity=raw.get("severity", "medium"),
                reason=raw.get("reason", ""),
                source="custom",
            )
        )
    return rules


def load_disabled_keys(path: "str | Path") -> set[tuple[str, str]]:
    path = Path(path)
    if not path.exists():
        return set()

    content = path.read_text(encoding="utf-8-sig")
    if path.suffix in (".yaml", ".yml"):
        import yaml

        data = yaml.safe_load(content)
    else:
        data = json.loads(content)

    if not isinstance(data, dict):
        return set()

    raw_rules = data.get("rules", [])
    if not isinstance(raw_rules, list):
        return set()

    disabled: set[tuple[str, str]] = set()
    for raw in raw_rules:
        if not raw.get("enabled", True):
            rule_type = raw.get("rule_type", "")
            column = raw.get("column", "")
            disabled.add((rule_type, column))
    return disabled


def load_severity_overrides(path: "str | Path") -> dict[tuple[str, str], str]:
    path = Path(path)
    if not path.exists():
        return {}

    content = path.read_text(encoding="utf-8-sig")
    if path.suffix in (".yaml", ".yml"):
        import yaml

        data = yaml.safe_load(content)
    else:
        data = json.loads(content)

    if not isinstance(data, dict):
        return {}

    raw_rules = data.get("rules", [])
    if not isinstance(raw_rules, list):
        return {}

    overrides: dict[tuple[str, str], str] = {}
    for raw in raw_rules:
        if "severity" in raw and raw.get("enabled", True):
            rule_type = raw.get("rule_type", "")
            column = raw.get("column", "")
            overrides[(rule_type, column)] = raw["severity"]
    return overrides


def merge_rules(
    auto_rules: list[RuleSuggestion],
    custom_rules: list[RuleSuggestion],
    disabled_keys: set[tuple[str, str]] | None = None,
    severity_overrides: dict[tuple[str, str], str] | None = None,
) -> list[RuleSuggestion]:
    disabled_keys = disabled_keys or set()
    severity_overrides = severity_overrides or {}

    custom_keys: set[tuple[str, str]] = set()
    for r in custom_rules:
        custom_keys.add((r.rule_type, r.column))

    seen: set[tuple[str, str]] = set()
    merged: list[RuleSuggestion] = []

    for r in auto_rules:
        key = (r.rule_type, r.column)
        if key in disabled_keys:
            continue
        if key in custom_keys:
            continue
        if key in seen:
            continue
        seen.add(key)
        if key in severity_overrides:
            r.severity = severity_overrides[key]
        merged.append(r)

    for r in custom_rules:
        key = (r.rule_type, r.column)
        if key in seen:
            continue
        seen.add(key)
        if key in severity_overrides:
            r.severity = severity_overrides[key]
        merged.append(r)

    return merged
